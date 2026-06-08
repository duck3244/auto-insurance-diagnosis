"""진단 엔진 (M4) — 통합 리스크 모델 → 맞춤 진단 리포트.

학습된 [빈도 GBM × 심도 GLM] + isotonic 재보정을 하나의 예측기로 묶고,
시장 분포 대비 백분위·grossing-up·보장 매칭(rules.py)으로 진단을 생성한다.

추론 시 train/inference skew 방지:
  - GLM 설계행렬은 학습 컬럼으로 reindex(미존재 더미=0).
  - LightGBM 범주형은 학습 카테고리로 정렬(unseen은 NaN→LightGBM 처리).
"""
from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

from auto_insurance.calibration.raking import bucket_age
from auto_insurance.data.split import train_test_split_grouped
from auto_insurance.diagnosis.rules import build_report
from auto_insurance.evaluation.calibration import apply_isotonic, fit_isotonic
from auto_insurance.features.encode import CATEGORICAL, NUMERIC
from auto_insurance.models.glm import fit_gamma_severity
from auto_insurance.models.weights import training_weight
from auto_insurance.pipeline import build_design, predict_glm, to_lgb_frame

_LGB = {"objective": "poisson", "metric": "poisson", "learning_rate": 0.05,
        "num_leaves": 31, "min_data_in_leaf": 100, "feature_fraction": 0.8,
        "bagging_fraction": 0.8, "bagging_freq": 1, "seed": 42,
        "verbose": -1, "num_threads": 4}


@dataclass
class DiagnosisEngine:
    freq_model: object              # LightGBM Booster (빈도율)
    sev_model: object              # statsmodels GLMResults (심도)
    iso: object                    # IsotonicRegression (재보정)
    market: np.ndarray             # 보정 순보험료 시장 분포(백분위 기준)
    cat_cols: list
    num_cols: list
    glm_columns: list              # 학습 GLM 설계행렬 컬럼
    cat_dtypes: dict               # LightGBM 범주형 카테고리
    loading: dict | None = None
    cohort_stats: dict | None = None   # T2: (연령밴드×Area) 순보험료 집계 (없으면 코호트 비교 생략)
    eda_stats: dict | None = None      # T3: rating factor별 청구빈도 집계 (없으면 EDA 패널 생략)

    # ---------- 예측 ----------
    def _lgb_frame(self, df):
        X, _ = to_lgb_frame(df, self.cat_cols, self.num_cols)
        for c, dt in self.cat_dtypes.items():
            X[c] = pd.Categorical(df[c], categories=dt)
        return X

    def _glm_frame(self, df):
        X = build_design(df, self.cat_cols, self.num_cols)
        return X.reindex(columns=self.glm_columns, fill_value=0.0)

    def pure_premium(self, df) -> np.ndarray:
        """순보험료(빈도율 × 심도), 재보정 전."""
        rate = np.asarray(self.freq_model.predict(self._lgb_frame(df)), float)
        sev = np.clip(predict_glm(self.sev_model, self._glm_frame(df)), 1e-3, None)
        return np.clip(rate * sev, 1e-8, None)

    def calibrated_pure_premium(self, df) -> np.ndarray:
        """isotonic 재보정 적용 순보험료."""
        return apply_isotonic(self.iso, self.pure_premium(df))

    def drivers(self, df, k=3) -> list:
        """이 정책의 SHAP 리스크 요인 상위 k (빈도 모델, 부호 포함)."""
        try:
            import shap
        except ImportError:
            return []
        if getattr(self, "_expl", None) is None:
            self._expl = shap.TreeExplainer(self.freq_model)
        X = self._lgb_frame(df)
        sv = np.asarray(self._expl.shap_values(X))[0]
        order = np.argsort(np.abs(sv))[::-1][:k]
        return [{"feature": str(X.columns[i]), "effect": round(float(sv[i]), 4)}
                for i in order]

    # ---------- 통계 ----------
    def market_stats(self, bins: int = 30) -> dict:
        """시장 순보험료 분포 요약(히스토그램·분위수) — 통계 가시화용.

        학습 시 저장된 self.market(전체 보정 순보험료 분포)에서 계산한다.
        긴 우측 꼬리 때문에 히스토그램은 p99 에서 클립해 가독성을 확보한다.
        """
        m = np.asarray(self.market, dtype=float)
        m = m[np.isfinite(m)]
        if m.size == 0:
            return {"n": 0, "quantiles": {}, "histogram": {"edges": [], "counts": []}}
        hi = float(np.quantile(m, 0.99))
        lo = float(m.min())
        if hi <= lo:
            hi = lo + 1.0
        counts, edges = np.histogram(np.clip(m, lo, hi), bins=max(5, int(bins)))
        qs = [10, 25, 50, 75, 90]
        return {
            "n": int(m.size),
            "mean": round(float(m.mean()), 2),
            "median": round(float(np.median(m)), 2),
            "min": round(lo, 2),
            "max": round(float(m.max()), 2),
            "p99": round(hi, 2),
            "quantiles": {str(q): round(float(np.quantile(m, q / 100)), 2) for q in qs},
            "histogram": {
                "edges": [round(float(e), 2) for e in edges],
                "counts": [int(c) for c in counts],
            },
        }

    def cohort_for(self, df, min_count: int = 30) -> dict | None:
        """T2: 입력과 같은 코호트(연령밴드×Area)의 순보험료 집계 + 내 위치.

        셀 표본이 부족하면(<min_count) 연령밴드 → 전체 순으로 폴백한다.
        cohort_stats 미보유(구버전 엔진)면 None.
        """
        cs = getattr(self, "cohort_stats", None)
        if not cs:
            return None
        ab = str(bucket_age(df["DrivAge"]).iloc[0])
        area = str(df["Area"].iloc[0])
        for key, label, level in (((ab, area), f"{ab} · Area {area}", "cell"),
                                  (ab, f"{ab} 연령대", "age")):
            table = cs["by_cell"] if level == "cell" else cs["by_age"]
            cell = table.get(key)
            if cell and cell["count"] >= min_count:
                return {"group": label, "level": level, **cell}
        return {"group": "전체 시장", "level": "overall", **cs["overall"]}

    # ---------- 진단 ----------
    def diagnose(self, row, with_drivers=True) -> dict:
        """단일 정책 → 맞춤 진단 리포트(백분위·보장·grossing-up·SHAP 요인·코호트)."""
        df = row.to_frame().T if isinstance(row, pd.Series) else row
        pp = float(self.calibrated_pure_premium(df)[0])
        drivers = self.drivers(df) if with_drivers else None
        report = build_report(pp, self.market, shap_top=drivers, loading=self.loading)
        cohort = self.cohort_for(df)
        if cohort:
            report["cohort"] = cohort
        if getattr(self, "eda_stats", None):
            # EDA 패널에서 사용자가 속한 밴드 하이라이트용
            report["bands"] = {f: (None if pd.isna(s.iloc[0]) else str(s.iloc[0]))
                               for f, s in feature_bands(df).items()}
        return report

    # ---------- 저장/로드 ----------
    def __getstate__(self):
        d = self.__dict__.copy()
        d.pop("_expl", None)               # SHAP explainer 캐시는 직렬화 제외
        return d

    def save(self, path):
        import joblib
        joblib.dump(self, path)

    @staticmethod
    def load(path):
        import joblib
        return joblib.load(path)


def _fit_freq_gbm(cfg, Xlgb, tr, cats, seed):
    """빈도 GBM — grouped 검증셋 early stopping."""
    tr2, val = train_test_split_grouped(tr, id_col="IDpol", test_size=0.15, seed=seed)
    w2 = training_weight(cfg, tr2, dataset="fremtpl2")
    wv = training_weight(cfg, val, dataset="fremtpl2")
    dtr = lgb.Dataset(Xlgb.loc[tr2.index], label=tr2.ClaimNb.to_numpy(), weight=w2,
                      init_score=np.log(np.clip(tr2.Exposure, 1e-6, None)),
                      categorical_feature=cats)
    dval = lgb.Dataset(Xlgb.loc[val.index], label=val.ClaimNb.to_numpy(), weight=wv,
                       init_score=np.log(np.clip(val.Exposure, 1e-6, None)), reference=dtr)
    return lgb.train(_LGB, dtr, num_boost_round=2000, valid_sets=[dval],
                     callbacks=[lgb.early_stopping(50, verbose=False)])


# --- T3 EDA: rating factor 밴딩 정의 (학습 집계 + 개인 밴드 하이라이트 공용) ---
_BONUS_BINS = [0, 60, 80, 100, 150, 1e9]
_BONUS_LABELS = ["50–59", "60–79", "80–99", "100–149", "150+"]
_VEHAGE_BINS = [0, 2, 6, 11, 16, 1e9]
_VEHAGE_LABELS = ["0–1", "2–5", "6–10", "11–15", "16+"]
_EDA_ORDER = {
    "DrivAge": ["<20", "20s", "30s", "40s", "50s", "60s", "70+"],
    "BonusMalus": _BONUS_LABELS,
    "VehAge": _VEHAGE_LABELS,
    "Area": list("ABCDEF"),
    "VehGas": ["Diesel", "Regular"],
}
_EDA_TITLES = {"DrivAge": "운전자 나이", "BonusMalus": "할인할증(BonusMalus)",
               "VehAge": "차령", "Area": "지역코드", "VehGas": "연료"}


def feature_bands(df) -> dict:
    """주요 rating factor 를 밴드 라벨 시리즈로 변환 (EDA 집계·개인 하이라이트 공용)."""
    num = lambda c: pd.to_numeric(df[c], errors="coerce")  # noqa: E731
    return {
        "DrivAge": bucket_age(df["DrivAge"]).astype(object),
        "BonusMalus": pd.cut(num("BonusMalus"), _BONUS_BINS, labels=_BONUS_LABELS,
                             right=False).astype(object),
        "VehAge": pd.cut(num("VehAge"), _VEHAGE_BINS, labels=_VEHAGE_LABELS,
                         right=False).astype(object),
        "Area": df["Area"].astype(object),
        # openml ARFF 는 nominal 을 따옴표로 감싼다("'Diesel'") → 표시·매칭 위해 정규화
        "VehGas": df["VehGas"].astype(str).str.strip("'\" ").astype(object),
    }


def _build_eda_stats(df) -> dict:
    """학습셋의 rating factor별 경험적 청구빈도(claims/exposure) 사전집계 — EDA 패널(T3)용.

    group 요약만 저장(수 KB). 밴드는 _EDA_ORDER 순서로 정렬해 차트 x축 일관성 유지.
    """
    exp = pd.to_numeric(df["Exposure"], errors="coerce").clip(lower=1e-6).to_numpy()
    cn = pd.to_numeric(df["ClaimNb"], errors="coerce").fillna(0).to_numpy()
    out = {}
    for feat, band in feature_bands(df).items():
        g = pd.DataFrame({"band": band, "cn": cn, "exp": exp})
        a = g.groupby("band", observed=True).agg(n=("cn", "size"), claims=("cn", "sum"),
                                                 exposure=("exp", "sum"))
        freq = (a["claims"] / a["exposure"]).to_dict()
        ns = a["n"].to_dict()
        out[feat] = {
            "title": _EDA_TITLES[feat],
            "bands": [{"band": b, "n": int(ns[b]), "frequency": round(float(freq[b]), 4)}
                      for b in _EDA_ORDER[feat] if b in ns],
        }
    return out


def _build_cohort_stats(df, premium) -> dict:
    """학습셋의 (연령밴드×Area) 순보험료 집계 — 코호트 비교(T2)용 사전계산 테이블.

    개별 row 가 아니라 group 요약만 저장(수 KB). 폴백용 연령밴드 단독 집계와
    전체 집계도 함께 보관한다.
    """
    g = pd.DataFrame({
        "age_band": bucket_age(df["DrivAge"]).astype("object"),
        "Area": df["Area"].astype("object"),
        "pp": np.asarray(premium, float),
    })

    def _agg(by):
        a = g.groupby(by, observed=True)["pp"].agg(["count", "mean", "median"])
        return {k: {"count": int(r["count"]), "mean": round(float(r["mean"]), 2),
                    "median": round(float(r["median"]), 2)}
                for k, r in a.iterrows()}

    return {
        "by_cell": _agg(["age_band", "Area"]),   # 키: (age_band, Area) 튜플
        "by_age": _agg("age_band"),              # 키: age_band
        "overall": {"count": int(len(g)), "mean": round(float(g.pp.mean()), 2),
                    "median": round(float(g.pp.median()), 2)},
    }


def fit_engine(cfg, df, seed=42) -> DiagnosisEngine:
    """df(전처리 완료)로 진단 엔진 학습. market = 학습셋 보정 순보험료 분포."""
    cat, num = CATEGORICAL, NUMERIC
    Xglm = build_design(df, cat, num)
    Xlgb, cats = to_lgb_frame(df, cat, num)

    freq_model = _fit_freq_gbm(cfg, Xlgb, df, cats, seed)

    claims = df[df.sev_count > 0]
    ysev = claims.sev_total / claims.sev_count
    wsev = training_weight(cfg, claims, dataset="fremtpl2")
    sev_model = fit_gamma_severity(Xglm.loc[claims.index], ysev, claims.sev_count,
                                   sample_weight=wsev)

    eng = DiagnosisEngine(
        freq_model=freq_model, sev_model=sev_model, iso=None, market=np.array([]),
        cat_cols=list(cat), num_cols=list(num), glm_columns=list(Xglm.columns),
        cat_dtypes={c: Xlgb[c].cat.categories for c in cats},
        loading=cfg.get("diagnosis", {}).get("loading"))

    raw_pp = eng.pure_premium(df)
    eng.iso = fit_isotonic(raw_pp, df.pure_premium,
                           weight=df.Exposure.to_numpy() * training_weight(cfg, df, "fremtpl2"))
    eng.market = eng.calibrated_pure_premium(df)
    eng.cohort_stats = _build_cohort_stats(df, eng.market)
    eng.eda_stats = _build_eda_stats(df)
    return eng
