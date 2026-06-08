"""M1 베이스라인 스크립트 헬퍼 스모크 테스트 (네트워크 불필요)."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "train_baseline.py"
_spec = importlib.util.spec_from_file_location("train_baseline", _SCRIPT)
tb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tb)


def _toy(n=200):
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "VehPower": rng.integers(4, 12, n), "VehAge": rng.integers(0, 20, n),
        "DrivAge": rng.integers(18, 90, n), "BonusMalus": rng.integers(50, 150, n),
        "Density": rng.integers(1, 3000, n),
        "VehBrand": rng.choice(["B1", "B2", "B12"], n),
        "VehGas": rng.choice(["Diesel", "Regular"], n),
        "Area": rng.choice(list("ABCDEF"), n),
        "Region": rng.choice(["R11", "R24", "R52"], n),
    })


def test_build_design_shapes_and_numeric():
    from auto_insurance.features.encode import CATEGORICAL, NUMERIC
    X = tb.build_design(_toy(), CATEGORICAL, NUMERIC)
    assert len(X) == 200
    assert X.shape[1] > len(NUMERIC)            # 더미 추가됨
    assert X.select_dtypes(exclude="number").empty   # 전부 수치형
    assert np.isfinite(X.to_numpy()).all()


def test_build_design_logs_density():
    df = _toy()
    X = tb.build_design(df, [], ["Density"])
    assert np.allclose(X["Density"].to_numpy(), np.log1p(df["Density"].astype(float)))
