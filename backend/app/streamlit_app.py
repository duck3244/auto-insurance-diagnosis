"""데모 앱 (M5, Streamlit) — 입력 폼 → 진단 리포트.

실행:  streamlit run app/streamlit_app.py
엔진:  python scripts/train_diagnosis.py  (models/diagnosis_engine.joblib)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auto_insurance.diagnosis.engine import DiagnosisEngine  # noqa: E402

ENGINE_PATH = ROOT / "models" / "diagnosis_engine.joblib"


@st.cache_resource
def get_engine():
    return DiagnosisEngine.load(ENGINE_PATH)


st.title("자동차보험 맞춤 진단")

if not ENGINE_PATH.exists():
    st.error("엔진이 없습니다. 먼저 `python scripts/train_diagnosis.py` 를 실행하세요.")
    st.stop()

eng = get_engine()
c1, c2 = st.columns(2)
inp = {
    "DrivAge": c1.number_input("운전자 나이", 16, 99, 40),
    "BonusMalus": c1.number_input("BonusMalus(할인할증)", 50, 350, 50),
    "VehPower": c1.number_input("차량 출력", 1, 15, 6),
    "VehAge": c1.number_input("차령", 0, 40, 2),
    "Density": c2.number_input("지역 인구밀도", 0, 30000, 1000),
    "VehBrand": c2.text_input("차량 브랜드", "B1"),
    "VehGas": c2.selectbox("연료", ["Regular", "Diesel"]),
    "Area": c2.selectbox("지역코드", list("ABCDEF"), index=2),
    "Region": c2.text_input("Region", "R24"),
}

if st.button("진단하기"):
    report = eng.diagnose(pd.DataFrame([inp]))
    cov = report["coverage"]
    st.metric("순보험료(리스크 원가)", f"€{report['pure_premium']:.1f}",
              f"시장 백분위 {report['risk_percentile']:.0f}%")
    st.metric("예상 상용보험료", f"€{report.get('estimated_gross_premium', 0):.1f}")
    st.write(f"**리스크 등급**: {cov['tier']} · 자기부담금 {cov['deductible']} · {cov['limit']}")
    if report.get("drivers"):
        st.write("**주요 리스크 요인(SHAP)**")
        st.table(pd.DataFrame(report["drivers"]))
    st.caption(report["disclaimer"])
    st.json(report)
