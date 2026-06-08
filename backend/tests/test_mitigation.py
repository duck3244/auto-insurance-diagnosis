"""완화 방안(§8.1) 스모크 테스트 — raking, grossing-up."""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from auto_insurance.calibration.raking import bucket_age, prepare_dataset, rake, rake_from_config
from auto_insurance.diagnosis.rules import build_report, gross_up

_CFG = yaml.safe_load(
    open(Path(__file__).resolve().parents[1] / "configs" / "config.yaml", encoding="utf-8"))


def test_raking_matches_target_margins():
    # 표본은 Male 80% 인데, 목표는 Male 50% → raking 후 가중 비율이 목표에 수렴
    df = pd.DataFrame({"Gender": ["Male"] * 80 + ["Female"] * 20})
    w = rake(df, {"Gender": {"Male": 0.5, "Female": 0.5}})
    male_share = w[df.Gender == "Male"].sum() / w.sum()
    assert abs(male_share - 0.5) < 1e-3
    assert abs(w.mean() - 1.0) < 1e-9   # 평균 1 정규화


def test_raking_empty_margins_returns_unit_weights():
    df = pd.DataFrame({"Gender": ["Male", "Female"]})
    w = rake(df, {"Gender": {}})        # config 스텁처럼 빈 마진
    assert np.allclose(w, 1.0)


def test_gross_up():
    # pure 750, 비용 0.25 + 이익 0.05 -> /0.70
    assert abs(gross_up(750.0, 0.25, 0.05) - 750.0 / 0.70) < 1e-9


def test_report_includes_gross_when_loading():
    market = np.linspace(0, 1000, 1000)
    rep = build_report(700.0, market, loading={"expense_ratio": 0.25, "profit_margin": 0.05})
    assert rep["estimated_gross_premium"] > rep["pure_premium"]


def test_bucket_age_labels():
    s = bucket_age([18, 25, 35, 45, 55, 65, 80])
    assert list(s) == ["<20", "20s", "30s", "40s", "50s", "60s", "70+"]


def test_fremtpl2_mapping_and_raking_converges():
    # freMTPL2 처럼 연속 DrivAge 만 있고 성별 없음 → DrivAge 만 적용되어야
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"DrivAge": rng.integers(18, 90, size=50_000)})
    mapped, margins = prepare_dataset(df, "fremtpl2", _CFG)
    assert set(margins) == {"DrivAge"}          # Gender 미적용(컬럼 없음)
    assert "DrivAge" in mapped.columns

    w = rake_from_config(df, _CFG, dataset="fremtpl2")
    band = bucket_age(df["DrivAge"])
    tgt = _CFG["mitigation"]["raking"]["target_margins"]["DrivAge"]
    for b, share in tgt.items():
        got = w[(band == b).to_numpy()].sum() / w.sum()
        assert abs(got - share) < 1e-3          # KOSIS 마진으로 수렴
    assert abs(w.mean() - 1.0) < 1e-9


def test_raking_disabled_returns_unit_weights():
    cfg = {"mitigation": {"raking": {"enabled": False}}}
    df = pd.DataFrame({"DrivAge": [20, 30, 40]})
    assert np.allclose(rake_from_config(df, cfg), 1.0)
