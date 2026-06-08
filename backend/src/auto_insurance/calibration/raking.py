"""Raking / IPF(Iterative Proportional Fitting) — §8.1 완화 방안.

한국 row-level 데이터는 비공개이고 공개된 것은 집계 통계뿐이므로,
**마진 분포(성별·연령·차종별 구성비)만으로** 학습 포트폴리오(freMTPL2 등)를
한국 모집단에 맞춰 가중 재조정한다(설문 post-stratification 표준).

원리: 각 범주변수의 marginal을 target에 맞도록 가중치를 순차 곱셈 업데이트,
수렴(영(0) 없으면 보장)할 때까지 반복. 결과 weight를 모델 학습/평가의
sample_weight 또는 진단 기준분포 재가중에 사용.

target margins 출처: KOSIS 집계통계(운전면허소지자·자동차등록대수). 수집은 kosis.py 참조.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rake(df: pd.DataFrame,
         target_margins: dict[str, dict],
         weight_col: str | None = None,
         max_iter: int = 50,
         tol: float = 1e-6) -> np.ndarray:
    """IPF로 sample weight 계산.

    Parameters
    ----------
    df : 원본 데이터(범주형 컬럼 포함).
    target_margins : {컬럼명: {범주값: 목표비율}}. 각 컬럼의 비율 합은 1 권장.
    weight_col : 초기 가중치 컬럼(없으면 1로 시작).
    max_iter, tol : 수렴 조건(마진 비율 최대 절대오차).

    Returns
    -------
    np.ndarray : 행별 raking weight (평균 1로 정규화).
    """
    n = len(df)
    w = np.ones(n) if weight_col is None else df[weight_col].to_numpy(dtype=float)

    # 빈/미지정 마진은 건너뜀 (config 스텁에서 {}로 비워둘 수 있음)
    margins = {c: m for c, m in target_margins.items() if m and c in df.columns}
    if not margins:
        return w / w.mean()

    cats = {c: df[c].astype("object").to_numpy() for c in margins}

    for _ in range(max_iter):
        max_dev = 0.0
        for col, targets in margins.items():
            values = cats[col]
            total = w.sum()
            for level, target_share in targets.items():
                mask = values == level
                cur = w[mask].sum() / total
                if cur > 0:
                    factor = target_share / cur
                    w[mask] *= factor
                    max_dev = max(max_dev, abs(target_share - cur))
        if max_dev < tol:
            break

    return w / w.mean()


# KOSIS 연령 마진과 동일한 밴드 (kosis.py 와 일치)
_AGE_BINS = [-np.inf, 20, 30, 40, 50, 60, 70, np.inf]
_AGE_LABELS = ["<20", "20s", "30s", "40s", "50s", "60s", "70+"]


def bucket_age(values) -> pd.Series:
    """연속 나이 → KOSIS 연령 밴드 라벨 (freMTPL2 DrivAge 등)."""
    return pd.cut(pd.to_numeric(values, errors="coerce"),
                  bins=_AGE_BINS, labels=_AGE_LABELS, right=False)


_TRANSFORMS = {
    "age_band": lambda s, spec: bucket_age(s),
    "value_map": lambda s, spec: s.map(spec.get("map", {})),
    "identity": lambda s, spec: s,
}


def prepare_dataset(df: pd.DataFrame, dataset: str, cfg: dict):
    """데이터셋별 컬럼 매핑 적용 → (매핑된 df, 적용할 target_margins) 반환.

    freMTPL2: 성별 컬럼 없음 → DrivAge(연속)만 밴드화해 적용.
    """
    rk = cfg["mitigation"]["raking"]
    target = rk.get("target_margins", {})
    ds = rk.get("datasets", {}).get(dataset)
    if not ds:
        raise KeyError(f"raking.datasets.{dataset} 설정이 없습니다.")

    out = df.copy()
    applicable = {}
    for margin in ds["margins"]:
        spec = ds["columns"][margin]
        src = spec["source"]
        if src not in out.columns:
            raise KeyError(f"[{dataset}] 컬럼 '{src}' 없음 (margin={margin})")
        fn = _TRANSFORMS[spec.get("transform", "identity")]
        out[margin] = fn(out[src], spec).astype("object")   # 마진키 이름으로 생성
        applicable[margin] = target[margin]
    return out, applicable


def rake_from_config(df: pd.DataFrame, cfg: dict,
                     dataset: str | None = None) -> np.ndarray:
    """config의 mitigation.raking 블록으로 raking 실행.

    dataset 지정 시 datasets.<dataset> 매핑(버킷팅·value_map)을 적용한 뒤 raking.
    미지정 시 df 컬럼이 마진 키와 이미 일치한다고 보고 직접 적용(하위호환).
    """
    rk = cfg.get("mitigation", {}).get("raking", {})
    if not rk.get("enabled", False):
        return np.ones(len(df))

    kw = dict(max_iter=rk.get("max_iter", 50), tol=float(rk.get("tol", 1e-6)))
    if dataset:
        mapped, margins = prepare_dataset(df, dataset, cfg)
        return rake(mapped, target_margins=margins, **kw)
    return rake(df, target_margins=rk.get("target_margins", {}), **kw)
