"""학습 스크립트 공용 헬퍼 — 로드·설계행렬·예측 (M1/M2 공유)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

_ROOT = Path(__file__).resolve().parents[2]


def load_raw(cfg, source: str = "auto", root: Path = _ROOT):
    """freMTPL2 freq/sev 로드. CSV 우선, 없으면 sklearn openml."""
    d = cfg["data"]
    fp, sp = root / d["freq_path"], root / d["sev_path"]
    if source == "csv" or (source != "openml" and fp.exists() and sp.exists()):
        print(f"[load] CSV: {fp.name}, {sp.name}")
        return pd.read_csv(fp), pd.read_csv(sp)
    print("[load] sklearn fetch_openml('freMTPL2freq' / 'freMTPL2sev') ...")
    from sklearn.datasets import fetch_openml
    freq = fetch_openml("freMTPL2freq", as_frame=True, parser="auto").frame
    sev = fetch_openml("freMTPL2sev", as_frame=True, parser="auto").frame
    if "IDpol" not in freq.columns:
        freq = freq.reset_index().rename(columns={"index": "IDpol"})
    return freq, sev


def coerce_numeric(freq, sev, cfg):
    for c in ("ClaimNb", "Exposure"):
        freq[c] = pd.to_numeric(freq[c], errors="coerce")
    amt = cfg["data"]["claim_amount_col"]
    sev[amt] = pd.to_numeric(sev[amt], errors="coerce")
    # openml ARFF 는 nominal 값을 따옴표로 감싼다(예: VehGas="'Diesel'") → 제거.
    # 안 하면 학습 카테고리("'Diesel'")가 폼/추론 입력("Diesel")과 불일치해 NaN 처리됨.
    from auto_insurance.features.encode import CATEGORICAL
    for c in CATEGORICAL:
        if c in freq.columns:
            freq[c] = freq[c].astype("string").str.strip("'\" ")
    return freq, sev


def build_design(df, cat_cols, num_cols):
    """GLM용 수치+더미(drop_first) 설계행렬. Density 로그변환."""
    num = df[num_cols].astype(float).copy()
    if "Density" in num:
        num["Density"] = np.log1p(num["Density"])
    parts = [num]
    for c in cat_cols:
        parts.append(pd.get_dummies(df[c].astype("category"),
                                    prefix=c, drop_first=True, dtype=float))
    return pd.concat(parts, axis=1)


def to_lgb_frame(df, cat_cols, num_cols):
    """LightGBM용 프레임 — 범주형은 category dtype(네이티브 처리). (X, cat_cols) 반환."""
    cols = [c for c in num_cols + cat_cols if c in df.columns]
    X = df[cols].copy()
    for c in num_cols:                       # 수치형 float 보장(단일행 object 방지)
        if c in X:
            X[c] = X[c].astype(float)
    if "Density" in X:
        X["Density"] = np.log1p(X["Density"])
    cats = []
    for c in cat_cols:
        if c in X:
            X[c] = X[c].astype("category")
            cats.append(c)
    return X, cats


def predict_glm(res, X, offset=None):
    """GLMResults 예측(상수 추가, 빈도는 offset=log exposure)."""
    Xc = sm.add_constant(X, has_constant="add")
    return np.asarray(res.predict(Xc, offset=offset), dtype=float)
