# 통계 기능 추가 가능성 검토

> 질문: 진단 웹앱에 **통계 기능**을 추가할 수 있는가?
> 작성일: 2026-06-07 · 결론: **가능. Tier 1(시장 분포 통계)은 이번에 구현·검증 완료.** Tier 2~3 은 학습단 데이터 보강 필요.

---

## 0. 핵심 전제 — 엔진이 이미 분포 데이터를 보유

`DiagnosisEngine`(`backend/src/auto_insurance/diagnosis/engine.py`)은 학습 시
**전체 학습셋의 보정 순보험료 분포**를 인스턴스 상태로 저장한다:

```python
eng.market = eng.calibrated_pure_premium(df)   # shape = (n_policies,)  ← joblib 에 함께 직렬화
```

이 배열은 원래 백분위(`risk_percentile`) 계산용이지만, **그대로 통계 패널의 원천**이 된다.
따라서 분포 기반 통계는 **추가 데이터·재학습 없이** 노출 가능하다.

---

## 1. Tier 1 — 시장 분포 통계 (✅ 구현·검증 완료)

`engine.market` 만으로 가능. 이번 작업에서 실제 추가함.

**백엔드** — `GET /market/stats?bins=N` (`engine.market_stats()`):
```json
{ "n": 32000, "mean": 164.13, "median": 75.25, "min": 0.0, "max": 2090.44, "p99": 1621.05,
  "quantiles": {"10":18.86,"25":36.87,"50":75.25,"75":170.16,"90":411.13},
  "histogram": {"edges":[...N+1...], "counts":[...N...]} }
```
- 우측 꼬리가 길어(평균≫중앙값) 히스토그램은 **p99 에서 클립**해 가독성 확보.
- 테스트: `tests/test_app.py::test_market_stats_endpoint` (edges=counts+1, Σcounts=n).

**프론트** — `MarketHistogram.jsx`: 분포 히스토그램 + **내 순보험료가 속한 구간 강조** + 요약(표본수·중앙값·평균). `PercentileGauge.jsx`: 백분위를 게이지로.

**이 티어로 답할 수 있는 질문**: "내 보험료는 시장 어디쯤인가", "중앙값/평균 대비 얼마인가", "상위 몇 %인가".

---

## 2. Tier 2 — 코호트/특성별 통계 (✅ 구현·검증 완료)

"나와 **같은 연령대/지역**의 평균은?" 같은 **조건부** 통계.

**제약(해결됨)**: `engine.market` 은 순보험료 **값만** 담아 group-by 불가였음.
→ 학습 시 *(연령밴드×Area)* 집계 테이블을 함께 저장하도록 보강.

**구현 내용**:
- `engine.py::_build_cohort_stats(df, premium)` — 학습셋을 `bucket_age(DrivAge)`(KOSIS 밴드)×`Area`
  로 group-by 해 `{by_cell, by_age, overall}` 집계(count/mean/median)를 저장. 개별 row 가 아니라
  요약만 → joblib 수 KB 증가. `fit_engine` 끝에서 `eng.cohort_stats` 채움.
- `engine.cohort_for(df, min_count=30)` — 입력의 (밴드, Area) 셀 조회, 표본 부족 시
  **연령밴드 → 전체 시장** 으로 폴백(레벨 표기). `diagnose()` 가 결과를 `report["cohort"]` 로 포함.
- 프론트 `CohortCompare.jsx` — 내 순보험료 vs 코호트 중앙값/평균 가로 막대 + "중앙값 대비 N배".
- 테스트 `test_diagnose_includes_cohort`. **엔진 재학습 필요**(`train_diagnosis.py` 로 joblib 재생성).

> 검증 예시(22세·Area F): cohort `20s · Area F`, 표본 113건, 중앙값 €170 / 평균 €292 →
> 내 순보험료 €852 = 중앙값 대비 **5.0배**. 같은 또래 안에서도 고위험임이 드러남.
>
> 주의: 셀 표본이 작으면(`min_count` 미만) 폴백 — UI 에 표본수·레벨을 함께 노출.

---

## 3. Tier 3 — EDA·요인별 통계 (✅ 구현·검증 완료)

특성별 **경험적 청구빈도**(claims/exposure)를 rating factor 밴드별로 보여주는 EDA 패널.

**제약(해결됨)**: 추론 서버는 학습 원자료를 들고 있지 않음 → "학습 시 사전집계해 엔진에 저장"으로 해결.

**구현 내용**:
- `engine.py::_build_eda_stats(df)` — `feature_bands()`(DrivAge·BonusMalus·VehAge·Area·VehGas 밴딩)로
  group-by 해 밴드별 `{n, frequency=Σclaims/Σexposure}` 사전집계. `fit_engine` 에서 `eng.eda_stats` 채움.
- `GET /market/eda` — 입력 무관 고정 응답(캐시 가능). `diagnose()` 는 사용자가 속한 밴드를
  `report["bands"]` 로 함께 반환(하이라이트용).
- 프론트 `EdaPanel.jsx` — 5개 소형 막대그래프 그리드, **내 밴드 indigo 강조**.
- 테스트 `test_market_eda_endpoint`, `test_diagnose_includes_bands`.

> 검증 인사이트(시장 32,000건): DrivAge `<20` 청구빈도 **0.43** vs 30~70대 ~0.09 ·
> BonusMalus `100–149` **0.27** 로 급증 · 신차(0–1) 0.16 · Area A 0.075→F 0.129 · 연료 Diesel≈Regular(영향 미미).
>
> ✅ **데이터 계약 버그 수정됨**(아래 4-2): VehGas 입력이 모델에 실제 반영된다.

---

## 4. 권장 로드맵

| 단계 | 기능 | 데이터 | 작업량 | 상태 |
|---|---|---|---|---|
| **T1** | 시장 분포 히스토그램·분위수·백분위 게이지 | `engine.market`(보유) | 小 | ✅ 완료 |
| **T2** | 코호트(연령·지역)별 평균/중앙값 비교 | 학습 시 집계 저장 + 재학습 | 中 | ✅ 완료 |
| **T3** | rating factor별 청구빈도 EDA 패널 | 학습 시 집계 저장 + 재학습 | 中 | ✅ 완료 |

**T1·T2·T3 모두 구현 완료.** 통계 패널은 엔진 사전집계(`market`/`cohort_stats`/`eda_stats`)
세 가지로 서빙되며, 추론 서버는 원자료 없이도 모든 통계를 제공한다.

### 4-2. VehGas 데이터 계약 수정 (✅ 완료)
T3 구현 중 발견 → 근본 수정. openml ARFF 가 nominal 을 따옴표로 감싸(`"'Diesel'"`) 학습 카테고리와
폼 입력(`"Diesel"`)이 불일치 → 예측 시 NaN(무시)되던 문제.
- **수정**: `pipeline.coerce_numeric` 에서 `CATEGORICAL` 컬럼의 따옴표/공백 제거(`.str.strip("'\" ")`).
  로드 직후 단일 지점이라 모든 학습 스크립트에 일괄 적용. 재학습으로 `cat_dtypes` 정규화.
- **검증**: `cat_dtypes['VehGas']=['Diesel','Regular']` · 입력이 결과를 바꿈(API/UI 모두
  Diesel €75.3 vs Regular €126.3) · 회귀 테스트 `test_coerce_numeric_strips_nominal_quotes`.

---

## 부록: 개선 여지 (T1)
- 히스토그램이 강하게 우편향 → **로그 스케일 x축** 또는 **분위수 기반 bin** 이 꼬리 가독성↑.
- `/market/stats` 는 입력 무관 고정 응답 → **응답 캐시**(엔진 1회 계산) 가능.
- Recharts 도입으로 번들 +약 360kB(gzip 173kB). 데모엔 무방하나, 경량화 필요 시 `manualChunks` 분리 권장.
