"""학습 가중치 연결(§8.1 raking → sample_weight) 테스트."""
import numpy as np
import pandas as pd
import pytest

from auto_insurance.models.weights import combine_weights, training_weight


def _cfg_raking_on():
    return {"mitigation": {"raking": {
        "enabled": True, "max_iter": 50, "tol": 1e-6,
        "target_margins": {"DrivAge": {
            "<20": 0.05, "20s": 0.15, "30s": 0.2, "40s": 0.2,
            "50s": 0.2, "60s": 0.1, "70+": 0.1}},
        "datasets": {"fremtpl2": {
            "margins": ["DrivAge"],
            "columns": {"DrivAge": {"source": "DrivAge", "transform": "age_band"}}}},
    }}}


def test_combine_weights():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([2.0, 2.0, 2.0])
    assert np.allclose(combine_weights(a, b), [2, 4, 6])
    assert np.allclose(combine_weights(a, None), a)     # None 무시
    assert combine_weights(None, None) is None


def test_training_weight_multiplies_base_and_raking():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"DrivAge": rng.integers(18, 90, size=2000)})
    exposure = np.full(len(df), 0.5)
    w = training_weight(_cfg_raking_on(), df, dataset="fremtpl2", base_weight=exposure)
    assert w is not None and len(w) == len(df)
    # base(0.5) × raking(평균1) → 평균≈0.5
    assert abs(w.mean() - 0.5) < 0.02


def test_gbm_frequency_runs_with_sample_weight():
    pytest.importorskip("lightgbm")
    from auto_insurance.models.gbm import fit_poisson_frequency
    rng = np.random.default_rng(1)
    n = 800
    X = pd.DataFrame({"f1": rng.normal(size=n), "f2": rng.normal(size=n)})
    exposure = rng.uniform(0.3, 1.0, n)
    y = rng.poisson(0.1 * exposure)
    w = rng.uniform(0.5, 1.5, n)            # raking 가중치 모사
    params = {"num_leaves": 7, "num_boost_round": 5, "verbose": -1}
    model = fit_poisson_frequency(X, y, exposure, params=params, sample_weight=w)
    assert len(model.predict(X)) == n


def test_glm_gamma_runs_with_sample_weight():
    pytest.importorskip("statsmodels.api")
    from auto_insurance.models.glm import fit_gamma_severity
    rng = np.random.default_rng(2)
    n = 300
    X = pd.DataFrame({"f1": rng.normal(size=n)})
    y = rng.gamma(2.0, 500.0, n)            # 양수 심도
    claim_count = rng.integers(1, 4, n)
    w = rng.uniform(0.5, 1.5, n)
    res = fit_gamma_severity(X, y, claim_count, sample_weight=w)
    assert res.params is not None
