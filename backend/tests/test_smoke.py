"""스모크 테스트 — 패키지 임포트 및 핵심 로직 동작 확인."""
import numpy as np
import pandas as pd

from auto_insurance.data.load import aggregate_severity, check_consistency
from auto_insurance.diagnosis.rules import build_report, recommend_coverage
from auto_insurance.evaluation.metrics import normalized_gini
from auto_insurance.pipeline import coerce_numeric


def test_consistency_report():
    freq = pd.DataFrame({"IDpol": [1, 2, 3], "ClaimNb": [1, 0, 1]})
    sev = pd.DataFrame({"IDpol": [1, 99], "ClaimAmount": [100.0, 50.0]})
    rep = check_consistency(freq, sev)
    assert rep["n_orphan_claims"] == 1          # IDpol 99
    assert rep["n_mismatched_policies"] == 1     # IDpol 3: ClaimNb=1, sev 없음


def test_aggregate_severity():
    sev = pd.DataFrame({"IDpol": [1, 1, 2], "ClaimAmount": [100.0, 50.0, 200.0]})
    agg = aggregate_severity(sev)
    assert agg.loc[agg.IDpol == 1, "sev_total"].iloc[0] == 150.0
    assert agg.loc[agg.IDpol == 1, "sev_count"].iloc[0] == 2


def test_diagnosis_report():
    market = np.linspace(0, 1000, 1000)
    rep = build_report(800.0, market)
    assert rep["risk_percentile"] > 50
    assert recommend_coverage(rep["risk_percentile"])["tier"] == "high_risk"
    assert "disclaimer" in rep


def test_coerce_numeric_strips_nominal_quotes():
    # openml ARFF 따옴표(VehGas="'Diesel'")가 제거되어 폼 입력과 일치해야 함
    freq = pd.DataFrame({"ClaimNb": [1], "Exposure": [1.0], "VehGas": ["'Diesel'"],
                         "Area": ["'C'"], "VehBrand": ["B1"], "Region": ["R24"]})
    sev = pd.DataFrame({"ClaimAmount": [100.0]})
    cfg = {"data": {"claim_amount_col": "ClaimAmount"}}
    out, _ = coerce_numeric(freq, sev, cfg)
    assert out["VehGas"].iloc[0] == "Diesel"     # 따옴표 제거
    assert out["Area"].iloc[0] == "C"
    assert out["VehBrand"].iloc[0] == "B1"        # 따옴표 없던 값은 그대로


def test_gini_monotone():
    y = np.array([0, 0, 1, 1, 5])
    perfect = normalized_gini(y, y)
    assert perfect > 0.9   # 완벽 예측은 정규화 Gini ≈ 1
