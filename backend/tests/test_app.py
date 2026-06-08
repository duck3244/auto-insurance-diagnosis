"""M5 데모 앱(FastAPI) 통합 테스트 — 작은 엔진 주입 후 /diagnose 호출."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from auto_insurance.config import load_config
from auto_insurance.diagnosis.engine import fit_engine

_APP = Path(__file__).resolve().parents[1] / "app" / "main.py"
_spec = importlib.util.spec_from_file_location("appmain", _APP)
appmain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(appmain)


def _toy(n=900):
    rng = np.random.default_rng(0)
    exp = rng.uniform(0.3, 1.0, n)
    cn = rng.poisson(0.15 * exp)
    df = pd.DataFrame({
        "IDpol": np.arange(n), "Exposure": exp, "ClaimNb": cn,
        "VehPower": rng.integers(4, 12, n), "VehAge": rng.integers(0, 20, n),
        "DrivAge": rng.integers(18, 90, n), "BonusMalus": rng.integers(50, 150, n),
        "Density": rng.integers(1, 3000, n),
        "VehBrand": rng.choice(["B1", "B2", "B12"], n),
        "VehGas": rng.choice(["Diesel", "Regular"], n),
        "Area": rng.choice(list("ABCDEF"), n),
        "Region": rng.choice(["R11", "R24", "R52"], n),
    })
    df["sev_count"] = np.where(cn > 0, cn, 0)
    df["sev_total"] = df["sev_count"] * rng.gamma(2.0, 800.0, n)
    df["pure_premium"] = df["sev_total"] / df["Exposure"].clip(lower=1e-6)
    return df


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    eng = fit_engine(load_config(), _toy(), seed=42)
    p = tmp_path_factory.mktemp("m") / "engine.joblib"
    eng.save(p)
    appmain.load_engine(p)                       # 엔진 주입
    return TestClient(appmain.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_diagnose_endpoint(client):
    payload = {"DrivAge": 40, "BonusMalus": 90, "VehPower": 6, "VehAge": 2,
               "Density": 1500, "VehBrand": "B1", "VehGas": "Regular",
               "Area": "C", "Region": "R24"}
    r = client.post("/diagnose", json=payload)
    assert r.status_code == 200
    rep = r.json()
    assert {"pure_premium", "risk_percentile", "coverage",
            "estimated_gross_premium"} <= set(rep)
    assert 0 <= rep["risk_percentile"] <= 100


def test_diagnose_includes_cohort(client):
    payload = {"DrivAge": 40, "BonusMalus": 90, "VehPower": 6, "VehAge": 2,
               "Density": 1500, "VehBrand": "B1", "VehGas": "Regular",
               "Area": "C", "Region": "R24"}
    rep = client.post("/diagnose", json=payload).json()
    assert "cohort" in rep                       # T2: 코호트 비교 포함
    coh = rep["cohort"]
    assert {"group", "level", "count", "mean", "median"} <= set(coh)
    assert coh["level"] in {"cell", "age", "overall"}
    assert coh["count"] > 0


def test_diagnose_includes_bands(client):
    payload = {"DrivAge": 22, "BonusMalus": 120, "VehPower": 6, "VehAge": 2,
               "Density": 1500, "VehBrand": "B1", "VehGas": "Diesel",
               "Area": "C", "Region": "R24"}
    rep = client.post("/diagnose", json=payload).json()
    assert "bands" in rep                        # T3: EDA 하이라이트용 개인 밴드
    assert rep["bands"]["DrivAge"] == "20s"
    assert rep["bands"]["BonusMalus"] == "100–149"


def test_market_eda_endpoint(client):
    r = client.get("/market/eda")
    assert r.status_code == 200
    eda = r.json()
    assert {"DrivAge", "BonusMalus", "VehAge", "Area", "VehGas"} <= set(eda)
    da = eda["DrivAge"]
    assert "title" in da and len(da["bands"]) > 0
    row = da["bands"][0]
    assert {"band", "n", "frequency"} <= set(row)
    assert row["frequency"] >= 0


def test_market_stats_endpoint(client):
    r = client.get("/market/stats?bins=12")
    assert r.status_code == 200
    s = r.json()
    assert s["n"] > 0
    assert {"mean", "median", "quantiles", "histogram"} <= set(s)
    hist = s["histogram"]
    # edges 는 counts 보다 1개 많아야 함 (np.histogram 규약)
    assert len(hist["edges"]) == len(hist["counts"]) + 1
    assert sum(hist["counts"]) == s["n"]            # 모든 표본이 한 구간에 속함


def test_diagnose_validation_error(client):
    r = client.post("/diagnose", json={"DrivAge": 10})   # BonusMalus<50 등 누락/범위밖
    assert r.status_code == 422


def test_form_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "맞춤 진단" in r.text
