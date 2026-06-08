# frontend

자동차보험 맞춤 진단 웹 UI — **React 19 + Vite 6 + Tailwind v3**. **Node 18 고정**(`.nvmrc`).

> 스택 선정 근거·제약은 [`../docs/frontend-tech-review.md`](../docs/frontend-tech-review.md) 참고.
> 핵심: Node 18 고정 → **Vite 6**(Vite 7은 Node 20.19+), **Tailwind v3**(v4 oxide 엔진이 Node 20+ 강제). 백엔드는 기존 FastAPI `POST /diagnose` 재사용.

## 실행
```bash
cd frontend
nvm use            # .nvmrc → Node 18.20.x
npm install
npm run dev        # http://localhost:5173  (/api → 127.0.0.1:8000 프록시)
```
백엔드도 함께 실행해야 진단이 동작한다:
```bash
cd backend
uvicorn app.main:app --reload          # 127.0.0.1:8000
# 엔진이 없으면(503): python scripts/train_diagnosis.py 먼저
```

## 빌드
```bash
npm run build      # → dist/  (FastAPI StaticFiles 로 서빙 가능)
npm run preview
```

## 구조
```
src/
  api/diagnose.js             # diagnose · fetchMarketStats · fetchEda 래퍼
                              #   POST /api/diagnose · GET /api/market/stats · GET /api/market/eda
  components/DriverForm.jsx    # 입력 폼 (DriverInput 9개 필드 + 검증)
  components/ReportCard.jsx    # 진단 결과 카드 오케스트레이터 (순보험료·백분위·보장 + 그래프)
  components/PercentileGauge.jsx # 리스크 백분위 게이지
  components/ShapChart.jsx       # SHAP 기여도 발산 막대그래프 (recharts)
  components/MarketHistogram.jsx # 시장 분포 히스토그램 + 내 위치 (recharts)
  components/CohortCompare.jsx   # 코호트(연령·지역) 평균/중앙값 비교 (recharts)
  components/EdaPanel.jsx        # 요율 인자별 청구빈도 EDA 그리드 (recharts)
  App.jsx                     # 전역 상태(report/error/loading) · 제출 처리
  index.css                   # @tailwind base/components/utilities
```
> 차트: **recharts**(React 19 호환). 통계 기능 검토는 [`../docs/statistics-feature-review.md`](../docs/statistics-feature-review.md).
