"""진단 엔진(M4) end-to-end 테스트 — 합성 데이터."""
import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

from auto_insurance.config import load_config
from auto_insurance.diagnosis.engine import DiagnosisEngine, fit_engine


def _toy(n=900):
    rng = np.random.default_rng(0)
    exp = rng.uniform(0.3, 1.0, n)
    claim_nb = rng.poisson(0.15 * exp)
    df = pd.DataFrame({
        "IDpol": np.arange(n), "Exposure": exp, "ClaimNb": claim_nb,
        "VehPower": rng.integers(4, 12, n), "VehAge": rng.integers(0, 20, n),
        "DrivAge": rng.integers(18, 90, n), "BonusMalus": rng.integers(50, 150, n),
        "Density": rng.integers(1, 3000, n),
        "VehBrand": rng.choice(["B1", "B2", "B12"], n),
        "VehGas": rng.choice(["Diesel", "Regular"], n),
        "Area": rng.choice(list("ABCDEF"), n),
        "Region": rng.choice(["R11", "R24", "R52"], n),
    })
    df["sev_count"] = np.where(claim_nb > 0, claim_nb, 0)
    df["sev_total"] = df["sev_count"] * rng.gamma(2.0, 800.0, n)
    df["pure_premium"] = df["sev_total"] / df["Exposure"].clip(lower=1e-6)
    return df


@pytest.fixture(scope="module")
def engine():
    cfg = load_config()
    return fit_engine(cfg, _toy(), seed=42), _toy()


def test_engine_market_and_prediction(engine):
    eng, df = engine
    assert isinstance(eng, DiagnosisEngine)
    assert len(eng.market) > 0
    pp = eng.calibrated_pure_premium(df.iloc[:10])
    assert len(pp) == 10 and np.isfinite(pp).all() and (pp >= 0).all()


def test_diagnose_report_structure(engine):
    eng, df = engine
    rep = eng.diagnose(df.iloc[[0]], with_drivers=False)
    assert {"pure_premium", "risk_percentile", "coverage",
            "estimated_gross_premium"} <= set(rep)
    assert 0 <= rep["risk_percentile"] <= 100
    assert rep["estimated_gross_premium"] > rep["pure_premium"]   # grossing-up


def test_save_load_roundtrip(engine, tmp_path):
    eng, df = engine
    p = tmp_path / "engine.joblib"
    eng.save(p)
    loaded = DiagnosisEngine.load(p)
    a = eng.calibrated_pure_premium(df.iloc[:5])
    b = loaded.calibrated_pure_premium(df.iloc[:5])
    assert np.allclose(a, b)                                       # 동일 예측
