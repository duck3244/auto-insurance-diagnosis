"""M2 GBM 스크립트 헬퍼 스모크 테스트 (빠른 합성 데이터)."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "train_gbm.py"
_spec = importlib.util.spec_from_file_location("train_gbm", _SCRIPT)
tg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tg)


def test_lgb_poisson_es_runs_and_predicts():
    rng = np.random.default_rng(0)
    n = 1200
    X = pd.DataFrame({"f1": rng.normal(size=n), "f2": rng.normal(size=n)})
    exp = rng.uniform(0.3, 1.0, n)
    y = rng.poisson(0.1 * exp)
    w = rng.uniform(0.5, 1.5, n)
    cut = 1000
    model = tg.lgb_poisson_es(
        X.iloc[:cut], y[:cut], exp[:cut], w[:cut],
        X.iloc[cut:], y[cut:], exp[cut:], w[cut:], cats=[])
    pred = model.predict(X)
    assert len(pred) == n and np.isfinite(pred).all()
    assert model.best_iteration >= 1


def test_search_tweedie_power_selects_from_grid():
    rng = np.random.default_rng(1)
    n = 1500
    df = pd.DataFrame({
        "IDpol": np.arange(n),
        "Exposure": rng.uniform(0.3, 1.0, n),
        "pure_premium": rng.gamma(0.05, 2000.0, n),   # 0 포함 우편향
        "f1": rng.normal(size=n),
    })
    Xlgb = df[["f1"]].copy()
    w = np.ones(n)
    best, scores = tg.search_tweedie_power(
        Xlgb, df, df.index, cats=[], grid=[1.5, 1.7, 1.9], w_rake=w, n_folds=2)
    assert best in (1.5, 1.7, 1.9)
    assert set(scores) == {1.5, 1.7, 1.9}
