import { useState } from 'react'

// DriverInput 스키마(backend/app/main.py) 와 1:1 대응. 숫자 필드는 min/max 검증 포함.
const NUMERIC_FIELDS = [
  { name: 'DrivAge', label: '운전자 나이', min: 16, max: 99, def: 40 },
  { name: 'BonusMalus', label: 'BonusMalus (할인할증)', min: 50, max: 350, def: 50 },
  { name: 'VehPower', label: '차량 출력', min: 1, max: 15, def: 6 },
  { name: 'VehAge', label: '차령', min: 0, max: 40, def: 2 },
  { name: 'Density', label: '지역 인구밀도', min: 0, max: 30000, def: 1000 },
]
const AREAS = ['A', 'B', 'C', 'D', 'E', 'F']
const GASES = ['Regular', 'Diesel']

const DEFAULTS = {
  DrivAge: 40, BonusMalus: 50, VehPower: 6, VehAge: 2, Density: 1000,
  VehBrand: 'B1', VehGas: 'Regular', Area: 'C', Region: 'R24',
}

const field = 'mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none'
const labelCls = 'block text-sm font-medium text-slate-700'

export default function DriverForm({ onSubmit, loading }) {
  const [form, setForm] = useState(DEFAULTS)

  const setNum = (name, value) => setForm((f) => ({ ...f, [name]: value === '' ? '' : Number(value) }))
  const setStr = (name, value) => setForm((f) => ({ ...f, [name]: value }))

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {NUMERIC_FIELDS.map((f) => (
          <label key={f.name} className={labelCls}>
            {f.label}
            <input
              className={field}
              type="number"
              min={f.min}
              max={f.max}
              required
              value={form[f.name]}
              onChange={(e) => setNum(f.name, e.target.value)}
            />
          </label>
        ))}

        <label className={labelCls}>
          차량 브랜드 (VehBrand)
          <input className={field} type="text" required value={form.VehBrand}
            onChange={(e) => setStr('VehBrand', e.target.value)} />
        </label>

        <label className={labelCls}>
          연료 (VehGas)
          <select className={field} value={form.VehGas} onChange={(e) => setStr('VehGas', e.target.value)}>
            {GASES.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </label>

        <label className={labelCls}>
          지역코드 (Area)
          <select className={field} value={form.Area} onChange={(e) => setStr('Area', e.target.value)}>
            {AREAS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>

        <label className={labelCls}>
          Region
          <input className={field} type="text" required value={form.Region}
            onChange={(e) => setStr('Region', e.target.value)} />
        </label>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-md bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? '진단 중…' : '진단하기'}
      </button>
    </form>
  )
}
