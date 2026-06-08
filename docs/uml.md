# UML 다이어그램

> 대상: **auto-insurance-diagnosis** · 작성일: 2026-06-07
> Mermaid 문법으로 작성(GitHub·대부분 마크다운 뷰어에서 렌더링). 전체 구조 설명은 [`architecture.md`](./architecture.md) 참고.

---

## 1. 백엔드 클래스 다이어그램 — 진단 엔진

핵심 서비스 `DiagnosisEngine` 와 협력 모델/규칙의 구성 관계.

```mermaid
classDiagram
    class DriverInput {
        <<Pydantic BaseModel>>
        +int VehPower
        +int VehAge
        +int DrivAge
        +int BonusMalus
        +int Density
        +str VehBrand
        +str VehGas
        +str Area
        +str Region
    }

    class DiagnosisEngine {
        <<dataclass>>
        +Booster freq_model
        +GLMResults sev_model
        +IsotonicRegression iso
        +ndarray market
        +list cat_cols
        +list num_cols
        +list glm_columns
        +dict cat_dtypes
        +dict loading
        +dict cohort_stats
        +dict eda_stats
        -TreeExplainer _expl
        +pure_premium(df) ndarray
        +calibrated_pure_premium(df) ndarray
        +drivers(df, k) list
        +market_stats(bins) dict
        +cohort_for(df) dict
        +diagnose(row) dict
        +save(path)
        +load(path)$ DiagnosisEngine
    }

    class rules {
        <<module>>
        +risk_percentile(pred, market) float
        +gross_up(pp, expense, profit) float
        +recommend_coverage(percentile) dict
        +build_report(...) dict
    }

    class fit_engine {
        <<factory>>
        +fit_engine(cfg, df) DiagnosisEngine
    }

    class FreqModel {
        <<LightGBM Booster>>
        +predict(X) ndarray
    }
    class SevModel {
        <<statsmodels GLMResults>>
        +predict(X) ndarray
    }
    class Isotonic {
        <<sklearn IsotonicRegression>>
        +predict(x) ndarray
    }

    DiagnosisEngine *-- FreqModel : freq_model
    DiagnosisEngine *-- SevModel : sev_model
    DiagnosisEngine *-- Isotonic : iso
    DiagnosisEngine ..> rules : build_report·percentile·coverage
    fit_engine ..> DiagnosisEngine : creates
    DiagnosisEngine ..> DriverInput : consumes(row)
```

---

## 2. 백엔드 모듈 의존 그래프 — 학습 파이프라인

`fit_engine` 이 호출하는 협력 모듈(데이터→보정→모델→평가).

```mermaid
flowchart TD
    fit["fit_engine(cfg, df)"]
    pipe["pipeline<br/>build_design · to_lgb_frame"]
    gbm["models.gbm<br/>fit_poisson_frequency"]
    glm["models.glm<br/>fit_gamma_severity"]
    weights["models.weights<br/>training_weight"]
    raking["calibration.raking<br/>rake_from_config"]
    kosis["calibration.kosis<br/>fetch_all_korea_margins"]
    calib["evaluation.calibration<br/>fit_isotonic"]
    eda["_build_eda_stats · _build_cohort_stats"]
    engine["DiagnosisEngine 인스턴스"]

    fit --> pipe
    fit --> gbm
    fit --> glm
    fit --> calib
    fit --> eda
    gbm --> weights
    glm --> weights
    weights --> raking
    raking --> kosis
    fit --> engine

    KOSIS["KOSIS OpenAPI<br/>(한국 통계)"]
    kosis --> KOSIS
```

---

## 3. 데이터 모델 — 입출력 스키마

요청(`DriverInput`)부터 응답(`DiagnosisReport`)까지의 데이터 형상.

```mermaid
classDiagram
    class DriverInput {
        int DrivAge
        int BonusMalus
        int VehPower
        int VehAge
        int Density
        str VehBrand
        str VehGas
        str Area
        str Region
    }

    class DiagnosisReport {
        float pure_premium
        float risk_percentile
        float estimated_gross_premium
        Coverage coverage
        Driver[] drivers
        Cohort cohort
        dict bands
        str disclaimer
    }
    class Coverage {
        str tier
        str deductible
        str limit
    }
    class Driver {
        str feature
        float effect
    }
    class Cohort {
        str group
        str level
        int count
        float mean
        float median
    }

    class MarketStats {
        int n
        float mean
        float median
        Histogram histogram
    }
    class Histogram {
        float[] edges
        int[] counts
    }

    class EdaResponse {
        FeatureEda[] features
    }
    class FeatureEda {
        str title
        Band[] bands
    }
    class Band {
        str band
        int n
        float frequency
    }

    DriverInput --> DiagnosisReport : POST /diagnose
    DiagnosisReport *-- Coverage
    DiagnosisReport *-- Driver
    DiagnosisReport *-- Cohort
    MarketStats *-- Histogram
    EdaResponse *-- FeatureEda
    FeatureEda *-- Band
```

---

## 4. 진단 요청 시퀀스 다이어그램

폼 제출부터 리포트 시각화까지의 전체 흐름(프록시·지연 후속 조회 포함).

```mermaid
sequenceDiagram
    actor User as 사용자
    participant Form as DriverForm
    participant App as App.jsx
    participant Api as api/diagnose.js
    participant FastAPI as FastAPI (main.py)
    participant Engine as DiagnosisEngine
    participant Card as ReportCard
    participant Hist as MarketHistogram
    participant Eda as EdaPanel

    User->>Form: 입력 + "진단하기" 클릭
    Form->>App: onSubmit(form)
    App->>App: setLoading(true)
    App->>Api: diagnose(form)
    Api->>FastAPI: POST /api/diagnose (Vite proxy)
    FastAPI->>FastAPI: Pydantic 검증 → DataFrame(1행)
    FastAPI->>Engine: get_engine().diagnose(df)
    Engine->>Engine: 빈도×심도 → isotonic
    Engine->>Engine: 백분위 → 보장 → SHAP → cohort
    Engine-->>FastAPI: report dict
    FastAPI-->>Api: 200 DiagnosisReport(JSON)
    Api-->>App: report
    App->>App: setReport(report), setLoading(false)
    App->>Card: render report

    Card->>Hist: mount
    Hist->>FastAPI: GET /api/market/stats?bins=24
    FastAPI-->>Hist: histogram
    Card->>Eda: mount
    Eda->>FastAPI: GET /api/market/eda
    FastAPI-->>Eda: feature bands
```

---

## 5. 프론트엔드 컴포넌트 다이어그램

React 컴포넌트 트리와 API 클라이언트 의존.

```mermaid
flowchart TD
    main["main.jsx<br/>createRoot"]
    App["App.jsx<br/>state: report·error·loading"]
    api["api/diagnose.js<br/>diagnose · fetchMarketStats · fetchEda"]
    Form["DriverForm<br/>state: form(9 필드)"]
    Card["ReportCard"]
    Gauge["PercentileGauge"]
    Shap["ShapChart"]
    Cohort["CohortCompare"]
    Hist["MarketHistogram"]
    Eda["EdaPanel"]
    recharts["recharts"]

    main --> App
    App --> Form
    App --> Card
    App -.import.-> api
    Card --> Gauge
    Card --> Shap
    Card --> Cohort
    Card --> Hist
    Card --> Eda
    Hist -.fetchMarketStats.-> api
    Eda -.fetchEda.-> api
    Shap --> recharts
    Cohort --> recharts
    Hist --> recharts
    Eda --> recharts
```

---

## 6. 학습/서빙 단계 흐름 (로드맵 M1~M5)

```mermaid
flowchart LR
    subgraph 오프라인 학습
        M1["M1 GLM 베이스라인<br/>data · models/glm"]
        M2["M2 GBM<br/>models/gbm · Tweedie 탐색"]
        M3["M3 평가/재보정<br/>evaluation · isotonic · SHAP"]
        M4["M4 엔진 학습·저장<br/>diagnosis/engine → joblib"]
        M1 --> M2 --> M3 --> M4
    end
    subgraph 온라인 서빙
        M5["M5 데모<br/>FastAPI · React SPA"]
    end
    M4 -.->|diagnosis_engine.joblib| M5
```
