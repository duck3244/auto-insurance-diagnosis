import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const ME = '#4f46e5'
const PEER = '#cbd5e1'
const LEVEL_NOTE = { age: '셀 표본 부족 → 연령대 기준', overall: '표본 부족 → 전체 시장 기준' }

// T2: 같은 코호트(연령밴드×Area)의 순보험료 중앙값/평균 대비 내 위치 비교.
// report.cohort = { group, level, count, mean, median }
export default function CohortCompare({ userPremium, cohort }) {
  if (!cohort || userPremium == null) return null
  const data = [
    { name: '내 순보험료', value: round1(userPremium), me: true },
    { name: '코호트 중앙값', value: cohort.median },
    { name: '코호트 평균', value: cohort.mean },
  ]
  const ratio = cohort.median > 0 ? userPremium / cohort.median : null
  const note = LEVEL_NOTE[cohort.level]

  return (
    <div className="mt-4">
      <h3 className="mb-1 text-sm font-semibold text-slate-700">같은 코호트와 비교</h3>
      <p className="mb-2 text-xs text-slate-500">
        <span className="font-medium text-indigo-600">{cohort.group}</span> · 표본{' '}
        {cohort.count.toLocaleString()}건{note && <span className="text-slate-400"> ({note})</span>}
      </p>
      <ResponsiveContainer width="100%" height={150}>
        <BarChart layout="vertical" data={data} margin={{ top: 4, right: 56, bottom: 4, left: 8 }}>
          <XAxis type="number" tickFormatter={(v) => `€${Math.round(v)}`} tick={{ fontSize: 11, fill: '#64748b' }} />
          <YAxis type="category" dataKey="name" width={96} tick={{ fontSize: 12, fill: '#334155' }} />
          <Tooltip cursor={{ fill: '#f1f5f9' }} formatter={(v) => [`€${v.toFixed(1)}`, '순보험료']} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.me ? ME : PEER} />
            ))}
            <LabelList
              dataKey="value"
              position="right"
              formatter={(v) => `€${Math.round(v)}`}
              style={{ fontSize: 11, fill: '#475569' }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {ratio != null && (
        <p className="mt-1 text-xs text-slate-500">
          동일 코호트 중앙값 대비{' '}
          <b className={ratio >= 1 ? 'text-red-500' : 'text-green-600'}>{ratio.toFixed(1)}배</b>
        </p>
      )}
    </div>
  )
}

const round1 = (v) => Math.round(v * 10) / 10
