import CohortCompare from './CohortCompare.jsx'
import EdaPanel from './EdaPanel.jsx'
import MarketHistogram from './MarketHistogram.jsx'
import PercentileGauge from './PercentileGauge.jsx'
import ShapChart from './ShapChart.jsx'

const eur = (v) => (typeof v === 'number' ? `€${v.toFixed(1)}` : '—')

function Metric({ label, value, sub }) {
  return (
    <div className="rounded-lg bg-slate-50 p-4">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-bold text-slate-900">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  )
}

// 진단 리포트(POST /diagnose 응답) 렌더 — 그래프 가시화 포함.
// 필드: pure_premium, risk_percentile, estimated_gross_premium,
//        coverage{tier,deductible,limit}, drivers[], disclaimer.
export default function ReportCard({ report }) {
  const cov = report.coverage ?? {}
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Metric
          label="순보험료 (리스크 원가)"
          value={eur(report.pure_premium)}
          sub={report.risk_percentile != null ? `시장 백분위 ${Math.round(report.risk_percentile)}%` : null}
        />
        <Metric label="예상 상용보험료" value={eur(report.estimated_gross_premium)} />
      </div>

      {report.risk_percentile != null && (
        <div className="rounded-lg border border-slate-200 p-4">
          <div className="mb-3 text-sm font-semibold text-slate-700">리스크 위치</div>
          <PercentileGauge percentile={report.risk_percentile} />
        </div>
      )}

      <div className="rounded-lg border border-slate-200 p-4">
        <div className="text-sm font-semibold text-slate-700">권장 보장</div>
        <div className="mt-2 flex flex-wrap gap-2 text-sm">
          {cov.tier != null && (
            <span className="rounded-full bg-indigo-100 px-3 py-1 font-medium text-indigo-700">
              리스크 등급: {cov.tier}
            </span>
          )}
          {cov.deductible != null && (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
              자기부담금: {cov.deductible}
            </span>
          )}
          {cov.limit != null && (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
              한도: {cov.limit}
            </span>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 p-4">
        <ShapChart drivers={report.drivers} />
      </div>

      {report.cohort && (
        <div className="rounded-lg border border-slate-200 p-4">
          <CohortCompare userPremium={report.pure_premium} cohort={report.cohort} />
        </div>
      )}

      <div className="rounded-lg border border-slate-200 p-4">
        <MarketHistogram userPremium={report.pure_premium} />
      </div>

      {report.bands && (
        <div className="rounded-lg border border-slate-200 p-4">
          <EdaPanel userBands={report.bands} />
        </div>
      )}

      {report.disclaimer && (
        <p className="text-xs leading-relaxed text-slate-400">{report.disclaimer}</p>
      )}
    </div>
  )
}
