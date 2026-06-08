import { useState } from 'react'
import { diagnose } from './api/diagnose.js'
import DriverForm from './components/DriverForm.jsx'
import ReportCard from './components/ReportCard.jsx'

export default function App() {
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (form) => {
    setLoading(true)
    setError(null)
    try {
      setReport(await diagnose(form))
    } catch (e) {
      setReport(null)
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 py-8">
      <main className="mx-auto max-w-3xl px-4">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900">자동차보험 맞춤 진단</h1>
          <p className="mt-1 text-sm text-slate-500">
            운전자·차량 정보로 순보험료(빈도×심도)·시장 백분위·권장 보장을 진단합니다.
          </p>
        </header>

        <div className="rounded-xl bg-white p-6 shadow-sm">
          <DriverForm onSubmit={handleSubmit} loading={loading} />
        </div>

        {error && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm whitespace-pre-line text-red-700">
            {error}
          </div>
        )}

        {report && (
          <div className="mt-6 rounded-xl bg-white p-6 shadow-sm">
            <ReportCard report={report} />
          </div>
        )}
      </main>
    </div>
  )
}
