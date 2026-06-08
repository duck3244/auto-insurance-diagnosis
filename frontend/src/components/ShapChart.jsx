import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

// 진단 리포트의 drivers[] (per-policy SHAP) 를 발산형 가로 막대그래프로 시각화.
// effect > 0 → 빈도(리스크) 증가(빨강), effect < 0 → 감소(초록).
const POS = '#ef4444'
const NEG = '#22c55e'

export default function ShapChart({ drivers }) {
  if (!Array.isArray(drivers) || drivers.length === 0) return null
  const data = drivers.map((d) => ({ name: d.feature, effect: d.effect }))
  const height = Math.max(140, data.length * 56)

  return (
    <div className="mt-4">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">주요 리스크 요인 (SHAP 기여도)</h3>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart layout="vertical" data={data} margin={{ top: 4, right: 56, bottom: 4, left: 8 }}>
          <XAxis type="number" tick={{ fontSize: 11, fill: '#64748b' }} />
          <YAxis
            type="category"
            dataKey="name"
            width={96}
            tick={{ fontSize: 12, fill: '#334155' }}
          />
          <Tooltip
            cursor={{ fill: '#f1f5f9' }}
            formatter={(v) => [v.toFixed(4), 'SHAP effect']}
          />
          <ReferenceLine x={0} stroke="#94a3b8" />
          <Bar dataKey="effect" radius={[4, 4, 4, 4]} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.effect >= 0 ? POS : NEG} />
            ))}
            <LabelList
              dataKey="effect"
              position="right"
              formatter={(v) => v.toFixed(3)}
              style={{ fontSize: 11, fill: '#475569' }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-1 text-xs text-slate-400">
        <span className="text-red-500">■</span> 리스크 증가 ·{' '}
        <span className="text-green-500">■</span> 리스크 감소 (빈도 모델 기준)
      </p>
    </div>
  )
}
