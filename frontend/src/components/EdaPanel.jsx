import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fetchEda } from '../api/diagnose.js'

const BAR = '#cbd5e1'
const MINE = '#4f46e5'
const FEATURE_ORDER = ['DrivAge', 'BonusMalus', 'VehAge', 'Area', 'VehGas']

// T3 EDA 패널 — rating factor별 시장 청구빈도(claims/exposure)를 소형 막대그래프 그리드로.
// 내가 속한 밴드(userBands)는 indigo 로 강조. (GET /api/market/eda)
export default function EdaPanel({ userBands }) {
  const [eda, setEda] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    fetchEda()
      .then((d) => alive && setEda(d))
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [])

  if (error) return <p className="mt-2 text-xs text-slate-400">EDA 통계를 불러오지 못했습니다.</p>
  if (!eda) return <p className="mt-2 text-xs text-slate-400">EDA 로딩…</p>

  const feats = FEATURE_ORDER.filter((f) => eda[f]?.bands?.length)

  return (
    <div className="mt-4">
      <h3 className="mb-1 text-sm font-semibold text-slate-700">리스크 요인별 청구빈도 (시장 전체)</h3>
      <p className="mb-3 text-xs text-slate-500">
        막대 = 밴드별 연간 청구빈도(claims/exposure) ·{' '}
        <span className="text-indigo-600">파란 막대</span> = 내가 속한 밴드
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {feats.map((f) => (
          <FeatureChart key={f} feat={eda[f]} userBand={userBands?.[f]} />
        ))}
      </div>
    </div>
  )
}

function FeatureChart({ feat, userBand }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-slate-600">{feat.title}</div>
      <ResponsiveContainer width="100%" height={150}>
        <BarChart data={feat.bands} margin={{ top: 4, right: 8, bottom: 4, left: -8 }}>
          <XAxis dataKey="band" tick={{ fontSize: 10, fill: '#94a3b8' }} interval={0} />
          <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(v) => v.toFixed(2)} width={36} />
          <Tooltip
            cursor={{ fill: '#f1f5f9' }}
            formatter={(v, _n, p) => [`${v.toFixed(4)} (${p.payload.n.toLocaleString()}건)`, '청구빈도']}
          />
          <Bar dataKey="frequency" radius={[3, 3, 0, 0]} isAnimationActive={false}>
            {feat.bands.map((b, i) => (
              <Cell key={i} fill={b.band === userBand ? MINE : BAR} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
