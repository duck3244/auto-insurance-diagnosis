"""ML 고도화 (M2) — Poisson/Tweedie GBM (LightGBM), 단조성 제약 옵션.

기대치: 빈도 Gini ≈ GBM 0.42 vs GLM 0.41 (공개 벤치마크) — modest lift.
심도는 claim 한정(26,639)으로 GLM 대비 이득 작을 수 있음.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np

from auto_insurance.models.weights import combine_weights


def fit_poisson_frequency(X, y_claim_nb, exposure, params=None, monotone=None,
                          sample_weight=None):
    """LightGBM Poisson 빈도. init_score = log(exposure)로 노출 반영.

    노출이 offset 으로 들어가므로 sample_weight 는 raking 가중치(평균 1)를 그대로 전달.
    """
    params = {"objective": "poisson", "metric": "poisson", **(params or {})}
    if monotone is not None:
        params["monotone_constraints"] = monotone
    dtrain = lgb.Dataset(X, label=y_claim_nb,
                         init_score=np.log(np.clip(exposure, 1e-6, None)),
                         weight=sample_weight)
    return lgb.train(params, dtrain)


def fit_tweedie_pure_premium(X, y_pure_premium, exposure, power=1.7, params=None,
                             sample_weight=None):
    """LightGBM Tweedie 순보험료 직접 모델. weight = exposure × raking(sample_weight)."""
    params = {"objective": "tweedie", "tweedie_variance_power": power, **(params or {})}
    weight = combine_weights(exposure, sample_weight)
    dtrain = lgb.Dataset(X, label=y_pure_premium, weight=weight)
    return lgb.train(params, dtrain)
