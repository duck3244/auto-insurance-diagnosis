"""학습 가중치 = 기저 가중치 × raking 가중치 (§8.1 한국 분포 보정 연결).

- 빈도(Poisson): 노출은 offset(=log exposure)로 들어가므로 sample_weight = raking_w.
- 심도(Gamma):   기저 weight = claim_count → sample_weight = claim_count × raking_w.
- 순보험료(Tweedie): 기저 weight = exposure → sample_weight = exposure × raking_w.

raking_w 는 rake_from_config 로 계산(평균 1 정규화). raking 비활성 시 1 벡터라
곱해도 기저 가중치를 그대로 보존한다.
"""
from __future__ import annotations

import numpy as np

from auto_insurance.calibration.raking import rake_from_config


def raking_weights(df, cfg, dataset: str | None = "fremtpl2") -> np.ndarray:
    """config 기반 raking 가중치(평균 1). 비활성 시 1 벡터."""
    return np.asarray(rake_from_config(df, cfg, dataset=dataset), dtype=float)


def combine_weights(*arrays) -> np.ndarray | None:
    """None 을 제외한 가중치 배열들을 원소별 곱. 모두 None 이면 None."""
    arrays = [np.asarray(a, dtype=float) for a in arrays if a is not None]
    if not arrays:
        return None
    out = arrays[0].copy()
    for a in arrays[1:]:
        out = out * a
    return out


def training_weight(cfg, df, dataset: str | None = "fremtpl2",
                    base_weight=None) -> np.ndarray | None:
    """base_weight(노출/클레임수 등)에 raking 가중치를 곱한 최종 sample_weight."""
    rw = raking_weights(df, cfg, dataset) if cfg else None
    return combine_weights(base_weight, rw)
