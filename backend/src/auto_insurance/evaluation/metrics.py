"""평가지표: deviance · Gini/Lift · auto-calibration (M3).

판별력(Gini/Lift)뿐 아니라 **auto-calibration**(교차보조 없는지)을 함께 검증.
GBM은 auto-calibrated가 아닌 경우가 많아 isotonic 재보정 권장.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import mean_gamma_deviance, mean_poisson_deviance, mean_tweedie_deviance

# numpy 2.0에서 np.trapz -> np.trapezoid 로 이름 변경 (구버전 호환)
_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))


def poisson_deviance(y_true, y_pred, sample_weight=None):
    return mean_poisson_deviance(y_true, y_pred, sample_weight=sample_weight)


def gamma_deviance(y_true, y_pred, sample_weight=None):
    return mean_gamma_deviance(y_true, y_pred, sample_weight=sample_weight)


def tweedie_deviance(y_true, y_pred, power=1.7, sample_weight=None):
    return mean_tweedie_deviance(y_true, y_pred, power=power, sample_weight=sample_weight)


def normalized_gini(y_true, y_pred, exposure=None):
    """노출 가중 정규화 Gini (계리 표준 lift 지표).

    전 타깃이 0(청구 없음)이거나 가중치 합이 0이면 lift 가 정의되지 않으므로 0.0 반환
    (분모 0 → nan/inf 방지).
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    w = np.ones_like(y_true) if exposure is None else np.asarray(exposure, dtype=float)

    w_total = w.sum()
    wy_total = (y_true * w).sum()
    if w_total <= 0 or wy_total <= 0:        # 가중치/타깃 전무 → lift 정의 불가
        return 0.0

    order = np.argsort(y_pred)[::-1]
    y_sorted, w_sorted = y_true[order], w[order]
    cum_w = np.cumsum(w_sorted) / w_total
    cum_y = np.cumsum(y_sorted * w_sorted) / wy_total
    gini = _trapz(cum_y, cum_w) - 0.5

    order_perfect = np.argsort(y_true)[::-1]
    cum_w_p = np.cumsum(w[order_perfect]) / w_total
    cum_y_p = np.cumsum((y_true * w)[order_perfect]) / wy_total
    gini_perfect = _trapz(cum_y_p, cum_w_p) - 0.5
    return gini / gini_perfect if gini_perfect else 0.0
