// 리스크 백분위(0~100)를 저위험→고위험 그라데이션 바 위 마커로 표시.
// percentile = 시장 분포에서 사용자보다 낮은(덜 위험한) 비율 → 클수록 고위험.
export default function PercentileGauge({ percentile }) {
  const p = Math.max(0, Math.min(100, Number(percentile) || 0))
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-500">
        <span>저위험</span>
        <span>고위험</span>
      </div>
      <div className="relative h-3 rounded-full bg-gradient-to-r from-green-400 via-yellow-400 to-red-500">
        <div
          className="absolute -top-1.5 h-6 w-1.5 -translate-x-1/2 rounded-full bg-slate-900 shadow"
          style={{ left: `${p}%` }}
          aria-label={`백분위 ${Math.round(p)}`}
        />
      </div>
      <div className="mt-2 text-center text-sm text-slate-600">
        시장의 <b className="text-slate-900">{Math.round(p)}%</b>보다 위험합니다
      </div>
    </div>
  )
}
