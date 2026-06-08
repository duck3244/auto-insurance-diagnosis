# 시스템 아키텍처

> 대상: **auto-insurance-diagnosis** — 개인 리스크(빈도×심도) 예측 → 적정 보장·보험료 진단/추천 시스템
> 작성일: 2026-06-07 · 범위: 백엔드(ML 파이프라인 + 서빙) · 프론트엔드(React SPA) 전체 구조

---

## 0. 개요 (TL;DR)

운전자/차량 정보를 입력받아 **청구 빈도(frequency)×심도(severity)** 를 예측하고 **순보험료(pure premium)** 를 산출한 뒤, 시장 분포 대비 백분위·권장 보장 수준·SHAP 리스크 요인을 **맞춤 진단 리포트**로 제공한다.

| 영역 | 스택 | 핵심 역할 |
|---|---|---|
| 모델링 | Python 3.11 · LightGBM · statsmodels · scikit-learn · SHAP | 빈도 GBM × 심도 GLM → 순보험료, isotonic 재보정 |
| 도메인 보정 | KOSIS OpenAPI · IPF raking | 프랑스(freMTPL2) 데이터를 한국 인구 분포로 보정 |
| 서빙 | FastAPI · Uvicorn (Streamlit 보조) | 학습된 엔진을 `joblib` 로드 → `POST /diagnose` |
| 웹 UI | React 19 · Vite 6 · Tailwind v3 · recharts | 입력 폼 → 진단 리포트 시각화 (Node 18 고정) |

**핵심 설계 원칙**: 계리 정석(frequency × severity 분리 모델링)을 따르고, 학습 시점에 통계량을 사전 계산하여 서빙은 무상태 단일 추론으로 처리한다.

---

## 1. 모노레포 구조

```
auto-insurance-diagnosis/
├── backend/    # Python — ML 파이프라인 + FastAPI/Streamlit 데모
├── frontend/   # React + Vite + Tailwind 웹 UI (MVP) — Node 18 고정
└── docs/       # 설계·기술 검토 문서
```

> 모든 Python 명령은 `backend/` 에서 실행한다(`cd backend`). 프론트엔드 개발 서버는 `/api` 경로를 백엔드(`127.0.0.1:8000`)로 프록시한다.

---

## 2. 전체 시스템 구성도

```
┌──────────────────────────────────────────────────────────────────────┐
│  FRONTEND (React SPA · Vite dev server :5173)                          │
│  DriverForm ──submit──> App ──> api/diagnose.js (fetch)                │
│  ReportCard <── report ── App                                          │
│     └ PercentileGauge · ShapChart · CohortCompare                      │
│        MarketHistogram · EdaPanel                                      │
└───────────────────────────┬──────────────────────────────────────────┘
                            │  /api/* (Vite proxy → rewrite)
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  BACKEND SERVING (FastAPI · Uvicorn :8000)  app/main.py                │
│  GET /health · GET /market/stats · GET /market/eda · POST /diagnose    │
│                            │                                           │
│                            ▼  get_engine() (lazy singleton)            │
│              ┌────────────────────────────────┐                       │
│              │  DiagnosisEngine (joblib 로드)  │                       │
│              │  freq(LightGBM) × sev(GLM)      │                       │
│              │  → isotonic → 백분위 → 보장/SHAP │                       │
│              └────────────────────────────────┘                       │
└──────────────────────────────────────────────────────────────────────┘
            ▲                                          ▲
            │ models/diagnosis_engine.joblib           │ (학습 단계)
            │                                          │
┌───────────┴──────────────────────────────────────────┴───────────────┐
│  TRAINING PIPELINE (scripts/ · 오프라인 배치)                          │
│  load_raw → preprocess → split → raking(KOSIS) → fit → calibrate       │
│  M1 GLM · M2 GBM · M3 평가/재보정 · M4 엔진 학습·저장                  │
└──────────────────────────────────────────────────────────────────────┘
            ▲
            │ KOSIS OpenAPI (한국 통계) · OpenML (freMTPL2 fallback)
```

---

## 3. 백엔드 아키텍처

### 3.1 기술 스택

| 분류 | 라이브러리 | 용도 |
|---|---|---|
| 언어/런타임 | Python 3.11+ | — |
| API 서버 | FastAPI 0.125 · Uvicorn 0.24 | 비동기 HTTP 서빙 |
| 보조 UI | Streamlit 1.28 | 인터랙티브 대시보드 |
| 데이터 | pandas 2.3 · numpy 2.4 | 전처리·집계 |
| GBM | LightGBM 4.6 · XGBoost 3.2 | 빈도(Poisson)·순보험료(Tweedie) |
| GLM | statsmodels 0.14 · scikit-learn 1.8 | 베이스라인(Poisson/Gamma) |
| 해석 | SHAP 0.51 | TreeExplainer 리스크 요인 |
| 보정 | scipy · sklearn isotonic | auto-calibration |
| 설정/직렬화 | PyYAML · python-dotenv · joblib | config·secret·엔진 저장 |

### 3.2 패키지 레이어 (`src/auto_insurance/`)

데이터가 흐르는 방향대로 계층이 분리되어 있다.

```
config.py        설정(YAML) + 시크릿(.env) 로더
pipeline.py      공용 헬퍼: load_raw · build_design · to_lgb_frame · predict_glm
│
├ data/          M1 — 로드·정합성검증·capping·고아 claim 처리 · policy 단위 split
├ features/      인코딩 정의 (CATEGORICAL / NUMERIC 컬럼)
├ calibration/   도메인 보정 — kosis(한국 마진 수집) · raking(IPF 가중치)
├ models/        glm(M1) · gbm(M2) · weights(raking→sample_weight)
├ evaluation/    M3 — metrics(deviance·Gini) · calibration(isotonic·balance)
└ diagnosis/     M4 — engine(통합 추론) · rules(백분위→보장 매핑)
```

### 3.3 서빙 레이어 (`app/`)

`app/main.py` 의 FastAPI 앱은 학습된 엔진을 **지연 로딩 싱글톤**(`get_engine()`)으로 보관하고 요청마다 단일 행 추론을 수행한다.

| 엔드포인트 | 메서드 | 입력 | 역할 |
|---|---|---|---|
| `/` | GET | — | 수동 테스트용 HTML 폼 |
| `/health` | GET | — | 헬스 체크 + `engine_loaded` 상태 |
| `/market/stats` | GET | `bins=30` | 시장 순보험료 분포(히스토그램·분위수) |
| `/market/eda` | GET | — | 요율 인자별 빈도 분석(T3 패널) |
| `/diagnose` | POST | `DriverInput` (JSON) | 맞춤 진단 리포트 |

요청 본문은 Pydantic `DriverInput` 으로 검증된다(범위 위반 시 HTTP 422). 엔진 미로딩/통계 부재 시 HTTP 503.

### 3.4 핵심 서비스: `DiagnosisEngine`

`diagnosis/engine.py` 의 `@dataclass DiagnosisEngine` 가 추론 전 과정을 캡슐화한다. 학습 시 `fit_engine(cfg, df)` 가 생성하고 `joblib` 로 저장한다.

보유 상태(학습 시 고정):
- `freq_model` (LightGBM Booster) · `sev_model` (statsmodels GLMResults) · `iso` (IsotonicRegression)
- `market` (보정된 시장 순보험료 분포) · `cohort_stats`(연령×지역 집계) · `eda_stats`(요율 인자 빈도)
- 컬럼/카테고리 메타: `cat_cols` · `num_cols` · `glm_columns` · `cat_dtypes`
- `_expl` (SHAP TreeExplainer) — 직렬화 제외, 최초 호출 시 지연 생성

`diagnose(row)` 오케스트레이션:
1. 빈도 예측 `freq_model.predict` × 심도 예측 `sev_model.predict` → 순보험료
2. `iso` 적용(isotonic 재보정)
3. `risk_percentile(pred, market)` 시장 백분위 산출
4. `recommend_coverage(percentile)` 보장 등급 결정
5. SHAP `drivers()` 상위 k개 리스크 요인 추출
6. `cohort_for()` 코호트(연령×지역) 비교 + `feature_bands()` EDA 하이라이트
7. `gross_up()` 영업보험료 환산 → `build_report()` 리포트 조립

### 3.5 도메인 보정 (raking)

freMTPL2(프랑스) 데이터를 한국 분포로 맞추기 위해 IPF(Iterative Proportional Fitting) raking 가중치를 학습에 주입한다.

```
kosis.fetch_all_korea_margins()  ─ KOSIS 2024 마진(성별·연령·차종) 수집
        │
raking.rake_from_config()        ─ IPF 반복 → mean=1 정규화 가중치
        │
weights.training_weight()        ─ base_weight(노출/claim수) × raking 가중치
        │
models.gbm / models.glm          ─ sample_weight 로 모델 학습에 반영
```

### 3.6 학습 파이프라인 (`scripts/`)

| 스크립트 | 단계 | 산출 |
|---|---|---|
| `train_baseline.py` | M1 | GLM 빈도(Poisson)+심도(Gamma) 베이스라인 |
| `train_gbm.py` | M2 | LightGBM vs GLM 비교 · Tweedie power 탐색(policy 단위 CV) |
| `evaluate_engine.py` | M3 | 순보험료 통합 · auto-calibration 검증 · isotonic 재보정 · SHAP |
| `train_diagnosis.py` | M4 | 전체 엔진 학습 → `models/diagnosis_engine.joblib` 저장 |

### 3.7 외부 연동

| 대상 | 용도 | 인증 |
|---|---|---|
| KOSIS OpenAPI | 한국 인구/면허/차량 마진(raking 타깃) | `KOSIS_API_KEY` (.env) |
| OpenML | freMTPL2 데이터 fallback 소스 | — |

---

## 4. 프론트엔드 아키텍처

### 4.1 기술 스택

| 분류 | 선택 | 비고 |
|---|---|---|
| 런타임 | React 19 | Hooks 기반 |
| 빌드 | Vite 6 | Node 18 고정 → Vite 7 불가 |
| CSS | Tailwind v3 + PostCSS + Autoprefixer | v4 oxide 엔진은 Node 20+ 요구 |
| 차트 | recharts 3.8 | Bar/BarChart 시각화 |
| HTTP | 네이티브 `fetch` | 별도 라이브러리 없음 |

자세한 선택 근거는 [`frontend-tech-review.md`](./frontend-tech-review.md) 참고.

### 4.2 디렉터리 구조

```
frontend/src/
├── main.jsx              React 루트 부트스트랩 (createRoot · StrictMode)
├── App.jsx               루트 컴포넌트 — 전역 상태(report/error/loading)·제출 처리
├── index.css            Tailwind 디렉티브
├── api/diagnose.js       백엔드 API 클라이언트 (diagnose · fetchMarketStats · fetchEda)
└── components/
    ├── DriverForm.jsx        입력 폼 (9개 운전자/차량 필드)
    ├── ReportCard.jsx        리포트 오케스트레이터
    ├── PercentileGauge.jsx   리스크 백분위 게이지 (presentational)
    ├── ShapChart.jsx         SHAP 요인 발산형 막대 차트
    ├── CohortCompare.jsx     사용자 vs 코호트 비교 차트
    ├── MarketHistogram.jsx   시장 분포 히스토그램 (mount 시 fetch)
    └── EdaPanel.jsx          요율 인자별 빈도 그리드 (mount 시 fetch)
```

### 4.3 상태 관리

**상태 관리 라이브러리 없음** — React `useState`/`useEffect` 만 사용(SPA·라우터 없음).

| 위치 | 상태 | 역할 |
|---|---|---|
| App | `report` · `error` · `loading` | 진단 결과·에러·로딩(폼 비활성화) |
| DriverForm | `form` | 9개 입력 필드 로컬 상태 |
| MarketHistogram | `stats` · `error` | mount 시 `fetchMarketStats(24)` |
| EdaPanel | `eda` · `error` | mount 시 `fetchEda()` |

단방향 데이터 흐름: App(상태 보유) → ReportCard(프롭 전달) → 시각화 자식. 시장 통계·EDA는 진단 호출과 무관하게 각 컴포넌트 mount 시 **병렬로** 독립 조회된다.

### 4.4 백엔드 통신 (`api/diagnose.js`)

```javascript
const BASE = import.meta.env.VITE_API_BASE ?? '/api'
```

| 함수 | 메서드 | 경로 | 호출 시점 |
|---|---|---|---|
| `diagnose(payload)` | POST | `/api/diagnose` | 폼 제출 |
| `fetchMarketStats(bins)` | GET | `/api/market/stats?bins=24` | MarketHistogram mount |
| `fetchEda()` | GET | `/api/market/eda` | EdaPanel mount |

개발 환경에서는 Vite 프록시가 `/api` → `127.0.0.1:8000` 로 rewrite 하여 CORS 없이 동일 출처처럼 호출한다. 503 응답 시 "엔진 학습 필요" 안내로 분기 처리한다.

---

## 5. End-to-End 요청 흐름

```
사용자 입력(DriverForm)
   └ onChange → form 상태 갱신
사용자 "진단하기" 클릭
   └ App.handleSubmit → setLoading(true)
       └ diagnose(form) ── POST /api/diagnose ──> Vite proxy ──> FastAPI
                                                                   │
   FastAPI: Pydantic 검증 → DataFrame(1행) → get_engine().diagnose()
       빈도×심도 → isotonic → 백분위 → 보장 → SHAP → 리포트 조립
                                                                   │
       <── DiagnosisReport(JSON) ──────────────────────────────────┘
   App: setReport(res) → setLoading(false)
       └ <ReportCard> 마운트
           ├ Metric · PercentileGauge · ShapChart · CohortCompare (프롭 즉시 렌더)
           ├ MarketHistogram → useEffect → GET /api/market/stats
           └ EdaPanel → useEffect → GET /api/market/eda
```

---

## 6. 주요 설계 결정 요약

| 결정 | 근거 |
|---|---|
| frequency × severity 분리 모델 | 계리 정석 — 빈도(LightGBM Poisson) × 심도(GLM Gamma) |
| 학습 시 통계량 사전 계산 | 서빙은 무상태 단일 추론 — 코호트/EDA/시장분포를 엔진에 내장 |
| 엔진 싱글톤 + joblib 직렬화 | 요청마다 모델 재로딩 회피, SHAP explainer는 지연 생성 |
| IPF raking 도메인 보정 | 프랑스 데이터를 한국(KOSIS 2024) 분포로 정합 |
| 프론트 상태 라이브러리 미도입 | 상태 3개·소규모 트리 — 로컬 state로 충분 |
| Vite dev proxy | CORS 설정 없이 `/api` 통합 |

> 클래스/시퀀스/컴포넌트 다이어그램은 [`uml.md`](./uml.md) 참고.
