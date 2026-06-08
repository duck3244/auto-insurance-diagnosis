"""GLM 베이스라인 (M1) — Poisson 빈도 + Gamma 심도, exposure 로그 오프셋.

계리 정석 베이스라인. ML 모델(gbm.py)의 lift 비교 기준.
"""
from __future__ import annotations

import numpy as np
import statsmodels.api as sm


def fit_poisson_frequency(X, y_claim_nb, exposure, sample_weight=None):
    """빈도 Poisson GLM. offset = log(exposure). sample_weight(raking)=var_weights."""
    offset = np.log(np.clip(exposure, 1e-6, None))
    model = sm.GLM(y_claim_nb, sm.add_constant(X),
                   family=sm.families.Poisson(), offset=offset,
                   var_weights=sample_weight)
    return model.fit()


def fit_gamma_severity(X, y_avg_claim, claim_count, sample_weight=None):
    """심도 Gamma GLM. freq_weights=claim 건수, var_weights=raking(sample_weight)."""
    model = sm.GLM(y_avg_claim, sm.add_constant(X),
                   family=sm.families.Gamma(link=sm.families.links.Log()),
                   freq_weights=claim_count, var_weights=sample_weight)
    return model.fit()
