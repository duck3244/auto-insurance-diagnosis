"""Auto-calibration 검증·isotonic 재보정 테스트 (M3)."""
import numpy as np

from auto_insurance.evaluation.calibration import (
    apply_isotonic,
    auto_calibration_error,
    balance_ratio,
    calibration_report,
    fit_isotonic,
)


def test_balance_ratio_perfect_and_biased():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert abs(balance_ratio(y, y) - 1.0) < 1e-9          # 완전 보정
    assert abs(balance_ratio(y, 2 * y) - 2.0) < 1e-9       # 2배 과대예측


def test_isotonic_fixes_balance_and_lowers_cohort_error():
    rng = np.random.default_rng(0)
    n = 5000
    y = rng.gamma(2.0, 1.0, n)
    pred = 1.6 * y + rng.normal(0, 0.1, n)                 # 과대예측·단조
    # train/test 분할
    tr, te = slice(0, 4000), slice(4000, n)
    iso = fit_isotonic(pred[tr], y[tr])
    cal = apply_isotonic(iso, pred[te])

    b_before = balance_ratio(y[te], pred[te])
    b_after = balance_ratio(y[te], cal)
    assert b_before > 1.3                                  # 원래 과대예측
    assert abs(b_after - 1.0) < abs(b_before - 1.0)        # balance 개선

    e_before = auto_calibration_error(y[te], pred[te])
    e_after = auto_calibration_error(y[te], cal)
    assert e_after <= e_before + 1e-9                      # cohort 오차 비증가


def test_auto_cal_error_robust_to_zero_pred():
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    pred = np.array([0.0, 0.0, 0.0, 5.0, 6.0, 7.0])        # 0 예측 포함 → 폭발 안 함
    e = auto_calibration_error(y, pred, n_bins=2)
    assert np.isfinite(e)


def test_calibration_report_keys():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    rep = calibration_report(y, 1.5 * y)
    assert set(rep) == {"balance", "auto_cal_error"}
