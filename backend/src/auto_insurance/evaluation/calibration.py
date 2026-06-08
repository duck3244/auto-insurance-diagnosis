"""Auto-calibration 검증 · isotonic 재보정 (M3).

- balance(전역 무편향): sum(w·pred)/sum(w·y) ≈ 1 이어야.
- auto-calibration error: 예측분위 cohort별 actual/pred 비율의 |비율−1| 평균(국소 무편향).
- isotonic 재보정: pred→E[y|pred] 단조매핑. **순위 보존 → Gini 불변, 보정만 개선**.
  GBM 은 auto-calibrated 가 아닌 경우가 많아 권장.
"""
from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression


def balance_ratio(y_true, y_pred, weight=None) -> float:
    """전역 balance = 가중평균(pred)/가중평균(actual). 1에 가까울수록 무편향."""
    y = np.asarray(y_true, float)
    p = np.asarray(y_pred, float)
    w = np.ones_like(y) if weight is None else np.asarray(weight, float)
    return float(np.average(p, weights=w) / np.average(y, weights=w))


def auto_calibration_error(y_true, y_pred, weight=None, n_bins=10) -> float:
    """cohort별 |actual−pred| 를 전역 평균으로 정규화한 가중 평균(노출 가중).

    ratio(=actual/pred) 방식은 pred≈0 cohort 에서 폭발하므로, 전역평균 대비
    절대 miscalibration 으로 측정(0=완전 보정). isotonic 같은 단조 보정의 효과를
    안정적으로 비교 가능.
    """
    import pandas as pd
    y = np.asarray(y_true, float)
    p = np.asarray(y_pred, float)
    w = np.ones_like(y) if weight is None else np.asarray(weight, float)
    d = pd.DataFrame({"y": y, "p": p, "w": w})
    d["bin"] = pd.qcut(d["p"].rank(method="first"), q=n_bins, labels=False)
    gmean = np.average(y, weights=w)
    err = 0.0
    for _, x in d.groupby("bin"):
        wsum = x["w"].sum()
        a = np.average(x["y"], weights=x["w"])
        f = np.average(x["p"], weights=x["w"])
        err += (wsum / w.sum()) * abs(a - f) / gmean
    return float(err)


def fit_isotonic(pred_train, y_train, weight=None) -> IsotonicRegression:
    """pred→actual 단조 보정기 학습(범위밖은 clip, 음수 방지)."""
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0)
    iso.fit(np.asarray(pred_train, float), np.asarray(y_train, float),
            sample_weight=None if weight is None else np.asarray(weight, float))
    return iso


def apply_isotonic(iso: IsotonicRegression, pred) -> np.ndarray:
    return np.asarray(iso.predict(np.asarray(pred, float)), float)


def calibration_report(y_true, y_pred, weight=None, n_bins=10) -> dict:
    """balance + auto-calibration error 요약."""
    return {
        "balance": balance_ratio(y_true, y_pred, weight),
        "auto_cal_error": auto_calibration_error(y_true, y_pred, weight, n_bins),
    }
