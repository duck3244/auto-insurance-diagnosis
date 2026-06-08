# MVP 프론트엔드 기술 검토

> 대상 스택: **Node 18(버전 고정) + React + Vite + Tailwind + FastAPI**
> 작성일: 2026-06-07 · 범위: 자동차보험 맞춤 진단 데모(M5)의 웹 UI를 Streamlit/인라인 HTML → React SPA 로 대체

---

## 0. 결론 (TL;DR)

| 항목 | 결정 | 이유 |
|---|---|---|
| Node | **18.20.x 고정** (`.nvmrc` + `engines`) | 사용자 요구 |
| 빌드 도구 | **Vite 6** (❌ Vite 7 아님) | **Vite 7은 Node 20.19+/22.12+ 필수 → Node 18에서 설치 불가** |
| UI 런타임 | **React 19** | Vite 6 + plugin-react v4 와 호환, Node 18 무관(브라우저 런타임) |
| CSS | **Tailwind v3** (`postcss` + `autoprefixer`) | ❗실측 검증: **Tailwind v4(4.3.x)의 native `@tailwindcss/oxide` 엔진이 Node ≥20 요구** → Node 18 빌드 실패. v3는 순수 JS라 Node 18 완전 호환 |
| API | **기존 FastAPI `POST /diagnose` 재사용** | 이미 구현·테스트됨(`backend/app/main.py`) |
| 개발 연동 | **Vite dev proxy** (`/api` → `127.0.0.1:8000`) | CORS 설정 없이 동일 출처처럼 호출 |

**핵심 리스크는 단 하나: Node 18 고정이 Vite 메이저 버전을 6으로 못박는다.** 나머지는 표준 구성으로 해결된다.

---

## 1. Node 18 고정이 부과하는 제약 (가장 중요)

Node 18은 **2025-04-30 EOL**. 그 결과 최신 프런트 툴체인이 빠르게 Node 18을 떨어뜨리고 있다.

| 패키지 | Node 18 지원? | 비고 |
|---|---|---|
| **Vite 7** (2025-06 출시) | ❌ | Node **20.19+ / 22.12+** 요구. ESM-only 전환 때문. Node 18에서 `npm i` 시 engine 경고/실패 |
| **Vite 6** | ✅ | Node **18.18.0+**, 20, 22 지원 (Node 21만 제외) |
| **Vite 5** | ✅ | Node 18 지원하나 굳이 구버전 쓸 이유 없음 |
| React 19 / react-dom 19 | ✅ | 브라우저 런타임이라 Node 버전 무관. 빌드는 Vite가 담당 |
| `@vitejs/plugin-react` v4 | ✅ | Vite 6 과 호환 |
| **Tailwind v4** (`tailwindcss`, `@tailwindcss/vite`) | ❌ | **실측: `@tailwindcss/oxide@4.3.0` 이 `engines: node >=20`. Node 18 에서 `Cannot find native binding` 으로 빌드 실패** (oxide 는 Rust 네이티브 바이너리) |
| **Tailwind v3** (`tailwindcss@3.4`, `postcss`, `autoprefixer`) | ✅ | 순수 JS, 네이티브 의존 없음 → Node 18 완전 호환. **본 프로젝트 채택** |

> **반드시 Vite `^6`, Tailwind `^3` 으로 고정**할 것.
> - `npm create vite@latest` 는 Vite 최신(=7)을 끌어오므로 그대로 쓰면 Node 18에서 깨진다 → `vite`/`@vitejs/plugin-react` 를 6.x/4.x 로 다운핀.
> - Tailwind v4 는 문서상 "Node 18 일반개발 OK" 처럼 보이지만, **실제 설치 시 transitive 네이티브 의존 `@tailwindcss/oxide` 가 Node 20+ 를 강제**한다(이 프로젝트에서 직접 재현·확인). Node 18 고정 동안은 v3 가 정답.

### Node 버전 고정 방법 (3중 잠금)
1. `frontend/.nvmrc` → `18.20.8` (또는 사내 표준 18.x 패치)
2. `frontend/package.json` → `"engines": { "node": ">=18.18 <19" }` + `"packageManager"` 명시
3. CI `actions/setup-node@v4` `node-version-file: frontend/.nvmrc` 로 동일 버전 강제

---

## 2. 실제 의존성 (`frontend/` — 스캐폴딩 완료, Node 18 빌드 검증)

```json
{
  "engines": { "node": ">=18.18 <19" },
  "dependencies": { "react": "^19.0.0", "react-dom": "^19.0.0", "recharts": "^3.8.1" },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^6.0.0",
    "tailwindcss": "^3.4.17",
    "postcss": "^8.4.49",
    "autoprefixer": "^10.4.20"
  }
}
```
> 실측 설치 결과(초기 스캐폴딩 시점): Vite **6.4.3**, EBADENGINE 경고 0, `npm run build` 성공(33 modules, CSS 9.7kB), dev 서버 HTTP 200.
> ※ 이후 통계 패널(T1~T3)을 위해 `recharts@^3.8.1` 를 추가 — 번들 +약 360kB(gzip 173kB). 상세는 [`statistics-feature-review.md`](./statistics-feature-review.md) 참고.

`vite.config.js` (React 플러그인 + dev 프록시. Tailwind 는 PostCSS 로 처리하므로 Vite 플러그인 불필요):
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true,
                       rewrite: (p) => p.replace(/^\/api/, '') } },
  },
})
```
Tailwind v3 설정 (3개 파일):
- `tailwind.config.js` → `content: ['./index.html', './src/**/*.{js,jsx}']`
- `postcss.config.js` → `plugins: { tailwindcss: {}, autoprefixer: {} }`
- `src/index.css` → `@tailwind base; @tailwind components; @tailwind utilities;`

---

## 3. 백엔드(FastAPI) 연동

기존 백엔드는 이미 MVP에 필요한 엔드포인트를 제공한다 — **신규 구현 불필요, 재사용**.

| 메서드 | 경로 | 입력 | 출력 |
|---|---|---|---|
| `GET` | `/health` | – | `{status, engine_loaded}` |
| `POST` | `/diagnose` | `DriverInput`(JSON) | 진단 리포트(JSON) |

`DriverInput` 필드(= 프론트 폼 입력): `VehPower, VehAge, DrivAge, BonusMalus, Density`(정수) · `VehBrand, VehGas, Area, Region`(문자열). → `backend/app/main.py:49`.

응답 리포트 렌더 대상: `pure_premium`, `risk_percentile`, `estimated_gross_premium`, `coverage{tier, deductible, limit}`, `drivers[]`(SHAP 상위 요인), `disclaimer`.

### 개발 연동 — 두 가지 선택지
- **A. Vite proxy (권장)**: 프론트는 `fetch('/api/diagnose')` → Vite가 `:8000` 으로 프록시. 백엔드 코드 변경 0. (위 `vite.config.js`)
- **B. CORS 미들웨어**: 프론트를 다른 출처/배포 도메인에서 직접 호출할 경우 백엔드에 추가:
  ```python
  from fastapi.middleware.cors import CORSMiddleware
  app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                     allow_methods=["*"], allow_headers=["*"])
  ```
  MVP 로컬 개발은 A 로 충분하고, 배포 단계에서 B 를 추가하는 것을 권장.

### 배포 형태
- **단순 MVP**: 프론트 `vite build` → 정적 산출물(`frontend/dist`)을 FastAPI `StaticFiles` 로 서빙(단일 포트, CORS 불필요).
- **분리 배포**: 프론트=정적호스팅(Netlify/S3 등), 백엔드=uvicorn. 이 경우 CORS(B) 필수.

---

## 4. MVP 기능 범위 (프론트)

기존 Streamlit/HTML 폼이 하던 일을 React 로 옮기는 것이 MVP. 신규 비즈니스 로직 없음.

1. **입력 폼** — `DriverInput` 9개 필드. 숫자 입력엔 min/max(예: DrivAge 16–99, BonusMalus 50–350) 검증, `VehGas`/`Area` 는 select.
2. **진단 호출** — `POST /api/diagnose`, 로딩/에러 상태 처리(엔진 미로드 시 503 → 안내 메시지).
3. **결과 카드** — 순보험료·시장 백분위, 예상 상용보험료, 리스크 등급(자기부담금/한도), SHAP 상위 요인 테이블, 면책 고지(disclaimer).
4. **반응형 레이아웃** — Tailwind 유틸리티, 모바일 1열 / 데스크톱 2열.

컴포넌트 구조(실제 구현):
```
frontend/src/
  api/diagnose.js               # fetch 래퍼 (diagnose · fetchMarketStats · fetchEda)
  components/DriverForm.jsx      # 입력 폼 (9 필드)
  components/ReportCard.jsx      # 리포트 오케스트레이터
  components/PercentileGauge.jsx # 백분위 게이지
  components/ShapChart.jsx       # SHAP 요인 막대 차트 (recharts)
  components/MarketHistogram.jsx # 시장 분포 히스토그램 (recharts)
  components/CohortCompare.jsx   # 코호트 비교 차트 (recharts)
  components/EdaPanel.jsx        # 요율 인자 EDA 그리드 (recharts)
  App.jsx
  index.css                      # @tailwind base; @tailwind components; @tailwind utilities;  (Tailwind v3 디렉티브)
```
> ⚠️ Tailwind **v3** 이므로 `index.css` 는 `@tailwind` 디렉티브 3줄을 쓴다. `@import "tailwindcss";` 는 v4 문법이라 본 구성에서 동작하지 않는다.

### 명시적 비범위 (MVP 이후)
- 인증/세션, 진단 이력 저장(현재 백엔드 stateless), 다국어, 상태관리 라이브러리(useState 로 충분).
- ~~차트 라이브러리~~ → **범위 편입**: 통계 패널(T1~T3) 구현으로 `recharts` 도입, SHAP·시장 분포·코호트·EDA 를 차트로 시각화([`statistics-feature-review.md`](./statistics-feature-review.md)).

---

## 5. 리스크 & 완화

| 리스크 | 영향 | 완화 |
|---|---|---|
| `create vite@latest` 가 Vite 7 설치 | Node 18에서 `npm i` 실패 | 생성 후 `vite@^6`, `@vitejs/plugin-react@^4` 로 **명시 고정** + `package-lock.json` 커밋 |
| Node 18 EOL(2025-04) | 보안 패치 종료, 툴 호환성 지속 축소 | MVP 검증 후 Node 20 LTS 승격 경로를 백로그에 명시. 고정은 `.nvmrc`/`engines`/CI 3중 |
| Tailwind v4 의 oxide 가 Node 20+ 강제 | Node 18 빌드 실패(재현됨) | **Tailwind v3 채택**으로 회피. Node 20 승격 시 v4 마이그레이션 검토 |
| 엔진 파일 부재 시 `/diagnose` 503 | 빈 화면 | 프론트에서 503 detail 표시 + `python scripts/train_diagnosis.py` 안내 |
| dev 포트 불일치(Vite 5173 ↔ FastAPI 8000) | CORS 에러 | Vite proxy(A) 기본 채택으로 회피 |

---

## 6. 진행 상태 / 다음 단계

**완료(스캐폴딩됨)** — `frontend/` 에 Vite 6 + React 19 + Tailwind v3 앱 구성, Node 18 에서 `build`/`dev` 검증:
- ✅ `package.json`(버전 고정) · `.nvmrc`(18.20.8) · `engines`
- ✅ `vite.config.js`(dev proxy `/api`→`:8000`) · Tailwind v3 3-파일 설정
- ✅ `api/diagnose.js`(`diagnose`/`fetchMarketStats`/`fetchEda`) + `DriverForm` / `ReportCard` 컴포넌트
- ✅ 기존 FastAPI `POST /diagnose` 연동
- ✅ 통계 패널(T1~T3): `PercentileGauge` / `ShapChart` / `MarketHistogram` / `CohortCompare` / `EdaPanel` (recharts) — [`statistics-feature-review.md`](./statistics-feature-review.md)
- ✅ `package-lock.json` 커밋(설치 재현성)

**남은 작업(백로그)**
1. 백엔드 실연동 E2E 확인: `cd backend && uvicorn app.main:app --reload` + `cd frontend && npm run dev` (엔진 없으면 `python scripts/train_diagnosis.py` 선행)
2. (배포 시) FastAPI `StaticFiles` 로 `frontend/dist` 서빙 또는 CORS 미들웨어 추가
3. CI 에 `frontend` job 추가(`setup-node@v4` `node-version-file: frontend/.nvmrc`) — `npm ci && npm run build`
4. Node 20 LTS 승격 경로(→ Vite 7 / Tailwind v4 마이그레이션) 별도 백로그

---

## 부록: 참고 출처
- [Vite 7.0 출시 — Node 18 드롭, Node 20.19+/22.12+ 요구](https://vite.dev/blog/announcing-vite7)
- [Vite 7.0 drops Node.js 18 (AlternativeTo)](https://alternativeto.net/news/2025/6/vite-7-0-drops-node-js-18-updates-browser-targets-and-adds-buildapp-hook/)
- [Vite 6.0 출시 — Node 18/20/22 지원](https://vite.dev/blog/announcing-vite6)
- [Vite Releases (버전별 Node 지원)](https://vite.dev/releases)
- [Tailwind CSS v4.0](https://tailwindcss.com/blog/tailwindcss-v4)
- [Tailwind v4 업그레이드 가이드(업그레이드 CLI Node 20 요구)](https://tailwindcss.com/docs/upgrade-guide)
