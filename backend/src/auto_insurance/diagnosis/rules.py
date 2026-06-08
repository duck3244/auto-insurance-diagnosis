"""진단/추천 레이어 (M4).

예측 순보험료 → 시장 분포 대비 백분위 → 보험료 구간 진단 + 권장 보장 매칭.
주의: 순보험료는 '리스크 원가'이며 실제 보험료(사업비·이익 마진 포함)와 다름 → 리포트에 명시.
"""
from __future__ import annotations

import numpy as np


def risk_percentile(pred, market_distribution):
    """개인 예측 순보험료의 시장 분포 대비 백분위(0~100)."""
    return float((np.asarray(market_distribution) < pred).mean() * 100)


def gross_up(pure_premium: float, expense_ratio: float = 0.25,
             profit_margin: float = 0.05) -> float:
    """순보험료(리스크 원가) → 상용보험료 (§8.1 grossing-up).

    gross = pure / (1 - expense_ratio - profit_margin)
    """
    denom = 1.0 - expense_ratio - profit_margin
    if denom <= 0:
        raise ValueError("expense_ratio + profit_margin must be < 1")
    return float(pure_premium) / denom


def recommend_coverage(percentile: float) -> dict:
    """리스크 백분위별 권장 자기부담금/담보 한도 룰 (예시 — 실데이터로 보정 필요)."""
    if percentile >= 70:
        return {"tier": "high_risk", "deductible": "상향(보험료 절감)", "limit": "필수 담보 중심"}
    if percentile >= 30:
        return {"tier": "standard", "deductible": "표준", "limit": "표준 패키지"}
    return {"tier": "low_risk", "deductible": "낮춤 가능", "limit": "보장 확대 여력"}


def build_report(pred_pure_premium: float, market_distribution, shap_top=None,
                 loading: dict | None = None) -> dict:
    """맞춤 진단 리포트 dict 생성. loading 제공 시 상용보험료 추정 포함."""
    pct = risk_percentile(pred_pure_premium, market_distribution)
    report = {
        "pure_premium": round(float(pred_pure_premium), 2),
        "risk_percentile": round(pct, 1),
        "coverage": recommend_coverage(pct),
        "drivers": shap_top or [],
        "disclaimer": "순보험료는 리스크 원가이며 실제 청구 보험료와 다릅니다.",
    }
    if loading:
        report["estimated_gross_premium"] = round(
            gross_up(pred_pure_premium, **loading), 2)
    return report
