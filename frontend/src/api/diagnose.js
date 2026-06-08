// 백엔드 FastAPI 진단 API 래퍼 — 엔드포인트는 이 파일 한 곳에서만 관리.
// dev: Vite proxy(/api → 127.0.0.1:8000). 배포 시 VITE_API_BASE 로 오버라이드.
const BASE = import.meta.env.VITE_API_BASE ?? '/api'

/**
 * 운전자·차량 정보 → 맞춤 진단 리포트.
 * @param {object} payload DriverInput (VehPower, VehAge, DrivAge, BonusMalus, Density, VehBrand, VehGas, Area, Region)
 * @returns {Promise<object>} 진단 리포트
 */
export async function diagnose(payload) {
  let res
  try {
    res = await fetch(`${BASE}/diagnose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new Error('백엔드에 연결할 수 없습니다. uvicorn 이 실행 중인지 확인하세요 (cd backend && uvicorn app.main:app --reload).')
  }

  if (!res.ok) {
    let detail = `요청 실패 (HTTP ${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 503) {
      detail += '\n→ 진단 엔진이 없습니다. `cd backend && python scripts/train_diagnosis.py` 를 먼저 실행하세요.'
    }
    throw new Error(detail)
  }
  return res.json()
}

/**
 * 시장 순보험료 분포 통계(히스토그램·분위수). 가시화/통계 패널용.
 * @param {number} bins 히스토그램 구간 수
 * @returns {Promise<object>} { n, mean, median, quantiles, histogram:{edges,counts}, ... }
 */
export async function fetchMarketStats(bins = 24) {
  const res = await fetch(`${BASE}/market/stats?bins=${bins}`)
  if (!res.ok) throw new Error(`시장 통계 요청 실패 (HTTP ${res.status})`)
  return res.json()
}

/**
 * rating factor별 청구빈도 EDA 집계(T3). 입력 무관·고정 응답.
 * @returns {Promise<object>} { DrivAge:{title,bands:[{band,n,frequency}]}, ... }
 */
export async function fetchEda() {
  const res = await fetch(`${BASE}/market/eda`)
  if (!res.ok) throw new Error(`EDA 통계 요청 실패 (HTTP ${res.status})`)
  return res.json()
}
