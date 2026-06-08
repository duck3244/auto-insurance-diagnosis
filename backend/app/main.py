"""데모 앱 (M5) — 운전자·차량 정보 입력 → 순보험료·보장 진단 (FastAPI).

저장된 진단 엔진(models/diagnosis_engine.joblib, M4)을 로드해 서빙.
엔진 생성:  python scripts/train_diagnosis.py

실행:
    uvicorn app.main:app --reload
    # http://127.0.0.1:8000/        (입력 폼)
    # http://127.0.0.1:8000/docs    (Swagger)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auto_insurance.diagnosis.engine import DiagnosisEngine  # noqa: E402

DEFAULT_ENGINE = ROOT / "models" / "diagnosis_engine.joblib"
app = FastAPI(title="auto-insurance-diagnosis", version="1.0")
_engine: DiagnosisEngine | None = None


def load_engine(path=None) -> DiagnosisEngine:
    """엔진 로드(주입/캐시). path 미지정 시 env 또는 기본 경로."""
    global _engine
    path = Path(path or os.environ.get("DIAGNOSIS_ENGINE_PATH", DEFAULT_ENGINE))
    if not path.exists():
        raise FileNotFoundError(
            f"엔진 파일 없음: {path}. 먼저 `python scripts/train_diagnosis.py` 실행.")
    _engine = DiagnosisEngine.load(path)
    return _engine


def get_engine() -> DiagnosisEngine:
    if _engine is None:
        load_engine()
    return _engine


class DriverInput(BaseModel):
    """freMTPL2 입력 변수 (Exposure 는 예측에 불필요·선택)."""
    VehPower: int = Field(6, ge=1, examples=[6])
    VehAge: int = Field(2, ge=0, examples=[2])
    DrivAge: int = Field(40, ge=16, examples=[40])
    BonusMalus: int = Field(50, ge=50, le=350, examples=[50])
    Density: int = Field(1000, ge=0, examples=[1000])
    VehBrand: str = Field("B1", examples=["B1"])
    VehGas: str = Field("Regular", examples=["Regular"])
    Area: str = Field("C", examples=["C"])
    Region: str = Field("R24", examples=["R24"])


@app.get("/health")
def health():
    return {"status": "ok", "engine_loaded": _engine is not None}


@app.get("/market/stats")
def market_stats(bins: int = 30):
    """시장 순보험료 분포 통계(히스토그램·분위수) — 가시화/통계용."""
    try:
        eng = get_engine()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return eng.market_stats(bins=bins)


@app.get("/market/eda")
def market_eda():
    """rating factor별 청구빈도 EDA 집계(T3) — 시장 전체. 입력 무관·캐시 가능."""
    try:
        eng = get_engine()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    stats = getattr(eng, "eda_stats", None)
    if not stats:
        raise HTTPException(status_code=503,
                            detail="EDA 통계 미보유 — 엔진 재학습 필요(python scripts/train_diagnosis.py).")
    return stats


@app.post("/diagnose")
def diagnose(payload: DriverInput):
    """운전자·차량 정보 → 맞춤 진단 리포트."""
    try:
        eng = get_engine()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    df = pd.DataFrame([data])
    return eng.diagnose(df)


@app.get("/", response_class=HTMLResponse)
def form():
    """간단 입력 폼(수동 테스트용)."""
    return """
    <html><body style="font-family:sans-serif;max-width:640px;margin:2rem auto">
    <h2>자동차보험 맞춤 진단</h2>
    <form id="f">
      DrivAge <input name="DrivAge" type="number" value="40"><br>
      BonusMalus <input name="BonusMalus" type="number" value="50"><br>
      VehPower <input name="VehPower" type="number" value="6">
      VehAge <input name="VehAge" type="number" value="2"><br>
      Density <input name="Density" type="number" value="1000"><br>
      VehBrand <input name="VehBrand" value="B1">
      VehGas <input name="VehGas" value="Regular">
      Area <input name="Area" value="C">
      Region <input name="Region" value="R24"><br><br>
      <button type="submit">진단</button>
    </form>
    <pre id="out"></pre>
    <script>
    f.onsubmit = async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(f));
      ["DrivAge","BonusMalus","VehPower","VehAge","Density"].forEach(k=>d[k]=+d[k]);
      const r = await fetch("/diagnose",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(d)});
      out.textContent = JSON.stringify(await r.json(), null, 2);
    };
    </script>
    </body></html>
    """
