import { useState } from 'react'
import { analyseUrl, fetchReport } from './api/wcag.js'
import UrlForm from './components/UrlForm.jsx'
import SummaryBar from './components/SummaryBar.jsx'
import FilterBar from './components/FilterBar.jsx'
import CriteriaList from './components/CriteriaList.jsx'
import RawApiPage from './pages/RawApiPage.jsx'

export default function App() {
  const [page, setPage]                 = useState('audit') // 'audit' | 'raw'
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState(null)
  const [result, setResult]             = useState(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [levelFilter, setLevelFilter]   = useState('all')
  const [auditUrl, setAuditUrl]         = useState(null)
  const [auditLang, setAuditLang]       = useState('en')
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError]   = useState(null)

  async function handleSubmit({ url, wcagVersion, lang }) {
    setLoading(true)
    setError(null)
    setResult(null)
    setStatusFilter('all')
    setLevelFilter('all')
    setAuditUrl(url)
    setAuditLang(lang || 'en')
    setReportError(null)
    try {
      const data = await analyseUrl(url, wcagVersion, lang)
      setResult(data)
    } catch (err) {
      setError(err.message || 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleOpenReport() {
    if (!auditUrl) return
    setReportLoading(true)
    setReportError(null)
    try {
      const html = await fetchReport(auditUrl, auditLang)
      const blob = new Blob([html], { type: 'text/html' })
      const url  = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener')
      // revoke after short delay so the new tab can load it
      setTimeout(() => URL.revokeObjectURL(url), 10000)
    } catch (err) {
      setReportError(err.message || 'Report generation failed')
    } finally {
      setReportLoading(false)
    }
  }

  const filteredCriteria = result
    ? result.criteria.filter(c => {
        if (statusFilter !== 'all' && c.status !== statusFilter) return false
        if (levelFilter  !== 'all' && c.level  !== levelFilter)  return false
        return true
      })
    : []

  const score = result ? (() => {
    const { passed, failed, needsReview } = result.summary
    const denom = passed + failed + needsReview
    return denom > 0 ? Math.round((passed / denom) * 100) : 0
  })() : null

  const levelAFailures = result?.criteria?.filter(c => c.level === 'A' && c.status === 'fail') ?? []
  const hasLevelAFail  = levelAFailures.length > 0
  const grade = score === null ? null
    : hasLevelAFail   ? 'F'
    : score >= 90 ? 'A'
    : score >= 75 ? 'B'
    : score >= 60 ? 'C'
    : score >= 40 ? 'D'
    : 'F'

  return (
    <div className="app">
      <div className="header">
        <h1>WCAG Compliance Checker</h1>
        <p>Automated accessibility audit against WCAG 2.1 and WCAG 2.2 success criteria</p>
      </div>

      <div className="page-tabs">
        <button
          className={`page-tab ${page === 'audit' ? 'active' : ''}`}
          onClick={() => setPage('audit')}
        >Audit View</button>
        <button
          className={`page-tab ${page === 'raw' ? 'active' : ''}`}
          onClick={() => setPage('raw')}
        >Raw API <code>/analyse-url</code></button>
      </div>

      {page === 'raw' && <RawApiPage />}

      {page === 'audit' && (
        <>
          <UrlForm onSubmit={handleSubmit} loading={loading} />

          {error && <div className="error-banner">Error: {error}</div>}

          {loading && (
            <div className="loading">
              <div className="spinner" />
              <div>Running analysis — this may take 30–60 seconds&hellip;</div>
            </div>
          )}

          {result && (
            <>
              <div className="meta-strip">
                <span>URL: <strong>{result.url}</strong></span>
                <span>WCAG {result.wcagVersion}</span>
                <span>Analysed at {new Date(result.analyzedAt).toLocaleTimeString()}</span>
                <button
                  className="report-btn"
                  onClick={handleOpenReport}
                  disabled={reportLoading}
                  title="Generate a visual HTML report with page screenshot and element overlays"
                >
                  {reportLoading ? (
                    <><span className="report-btn-spinner" /> Generating…</>
                  ) : (
                    '⬛ Visual Report'
                  )}
                </button>
              </div>

              {reportError && (
                <div className="error-banner" style={{ margin: '0 0 8px' }}>
                  Report error: {reportError}
                </div>
              )}

              <SummaryBar summary={result.summary} score={score} grade={grade} hasLevelAFail={hasLevelAFail} levelAFailures={levelAFailures} />

              <FilterBar
                summary={result.summary}
                statusFilter={statusFilter}
                levelFilter={levelFilter}
                onStatusChange={setStatusFilter}
                onLevelChange={setLevelFilter}
              />

              <CriteriaList
                criteria={filteredCriteria}
                totalCount={result.criteria.length}
              />
            </>
          )}
        </>
      )}
    </div>
  )
}
