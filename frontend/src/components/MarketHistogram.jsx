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
import { fetchMarketStats } from '../api/diagnose.js'

const BAR = '#cbd5e1'
const USER = '#4f46e5'

// 시장 순보험료 분포 히스토그램. 사용자의 순보험료가 속한 구간을 강조해
// "내가 시장 어디쯤인가" 를 직관적으로 보여준다. (GET /api/market/stats)
export default function MarketHistogram({ userPremium }) {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    fetchMarketStats(24)
      .then((s) => alive && setStats(s))
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [])

  if (error) return <p className="mt-2 text-xs text-slate-400">시장 분포 통계를 불러오지 못했습니다.</p>
  if (!stats) return <p className="mt-2 text-xs text-slate-400">시장 분포 로딩…</p>

  const { edges, counts } = stats.histogram
  const data = counts.map((c, i) => ({
    label: Math.round(edges[i]),
    lo: edges[i],
    hi: edges[i + 1],
    count: c,
  }))

  // 사용자 순보험료가 속한 구간 인덱스 (p99 초과면 마지막 구간)
  const userIdx =
    userPremium == null
      ? -1
      : Math.min(
          data.length - 1,
          data.findIndex((d) => userPremium >= d.lo && userPremium < d.hi),
        )
  const userBin = userPremium != null && userIdx >= 0 ? userIdx : data.length - 1

  return (
    <div className="mt-4">
      <h3 className="mb-1 text-sm font-semibold text-slate-700">시장 순보험료 분포에서 내 위치</h3>
      <p className="mb-2 text-xs text-slate-500">
        표본 {stats.n.toLocaleString()}건 · 중앙값 €{stats.median} · 평균 €{stats.mean}
        {userPremium != null && (
          <>
            {' '}· <span className="font-medium text-indigo-600">내 순보험료 €{userPremium.toFixed(1)}</span>
          </>
        )}
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: '#94a3b8' }}
            tickFormatter={(v) => `€${v}`}
            interval={3}
          />
          <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: '#f1f5f9' }}
            formatter={(v) => [v.toLocaleString(), '정책 수']}
            labelFormatter={(_, p) =>
              p?.[0] ? `€${Math.round(p[0].payload.lo)}–€${Math.round(p[0].payload.hi)}` : ''
            }
          />
          <Bar dataKey="count" radius={[3, 3, 0, 0]} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={i} fill={i === userBin ? USER : BAR} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-1 text-xs text-slate-400">
        <span className="text-indigo-600">■</span> 내 위치 · 회색 = 시장 분포 (우측 꼬리는 p99 에서 클립)
      </p>
    </div>
  )
}
