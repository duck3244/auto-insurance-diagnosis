"""freMTPL2 데이터 로드 · 정합성 검증 · 전처리 (M1).

freMTPL2 알려진 이슈:
  - freq.ClaimNb 와 sev 매칭 claim 수 불일치 정책 ~9,117 / 678,013
  - freq에 대응 정책 없는 고아 claim ~195 / 26,639
  - ClaimNb/Exposure 이상치 → capping 권장 (ClaimNb<=4, Exposure<=1)
"""
from __future__ import annotations

import pandas as pd


def aggregate_severity(sev: pd.DataFrame, id_col: str = "IDpol",
                       amount_col: str = "ClaimAmount") -> pd.DataFrame:
    """policy 단위 총 claim 금액·건수 집계."""
    agg = (sev.groupby(id_col)[amount_col]
              .agg(sev_total="sum", sev_count="count")
              .reset_index())
    return agg


def check_consistency(freq: pd.DataFrame, sev: pd.DataFrame,
                      id_col: str = "IDpol",
                      claim_count_col: str = "ClaimNb") -> dict:
    """정합성 리포트: 불일치 정책 수 · 고아 claim 수 반환."""
    sev_agg = aggregate_severity(sev, id_col)
    merged = freq.merge(sev_agg, on=id_col, how="left")
    mismatched = (merged["sev_count"].fillna(0) != merged[claim_count_col]) & \
                 (merged[claim_count_col] > 0)
    orphan = ~sev[id_col].isin(set(freq[id_col]))
    return {
        "n_policies": len(freq),
        "n_claim_records": len(sev),
        "n_mismatched_policies": int(mismatched.sum()),
        "n_orphan_claims": int(orphan.sum()),
    }


def preprocess(freq: pd.DataFrame, sev: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """capping · 고아 claim 처리 · freq-sev 결합 → policy 단위 학습 테이블.

    반환 컬럼(추가): sev_total, sev_count, pure_premium(=sev_total/Exposure).
    """
    p = cfg["preprocess"]
    id_col = cfg["data"]["id_col"]
    exposure_col = cfg["data"]["exposure_col"]
    claim_col = cfg["data"]["claim_count_col"]

    freq = freq.copy()
    freq[claim_col] = freq[claim_col].clip(upper=p["cap_claim_nb"])
    freq[exposure_col] = freq[exposure_col].clip(upper=p["cap_exposure"])

    amount_col = cfg["data"]["claim_amount_col"]
    if p.get("drop_orphan_claims", True):
        sev = sev[sev[id_col].isin(set(freq[id_col]))]

    # 심도 대형 claim 우편향 → 상위 분위 클리핑(과대예측 방지, §2.1)
    q = p.get("severity_clip_quantile")
    if q:
        sev = sev.copy()
        sev[amount_col] = sev[amount_col].clip(upper=sev[amount_col].quantile(q))

    sev_agg = aggregate_severity(sev, id_col, amount_col)
    df = freq.merge(sev_agg, on=id_col, how="left")
    df["sev_total"] = df["sev_total"].fillna(0.0)
    df["sev_count"] = df["sev_count"].fillna(0).astype(int)
    df["pure_premium"] = df["sev_total"] / df[exposure_col].clip(lower=1e-6)
    return df
