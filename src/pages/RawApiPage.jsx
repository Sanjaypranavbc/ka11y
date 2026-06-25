import { useState } from 'react'
import { analyseUrlRaw, fetchReport } from '../api/wcag.js'
import UrlForm from '../components/UrlForm.jsx'

const STATUS_COLOR = {
  fail:           '#dc2626',
  needs_review:   '#d97706',
  incomplete:     '#d97706',
  pass:           '#16a34a',
  not_applicable: '#94a3b8',
  not_checked:    '#94a3b8',
  manual_only:    '#6366f1',
}

function ElementCard({ el }) {
  const html     = el.html || el.snippet
  const selector = el.selector
    || (typeof el.target === 'string' ? el.target : null)
    || (Array.isArray(el.target) ? el.target[0] : null)
  const bbox     = el.bounding_box

  return (
    <div className="raw-element">
      {html && (
        <code className="raw-element-snippet">{html}</code>
      )}
      {selector && (
        <div className="raw-element-meta">
          <span className="raw-el-label">Selector</span>
          <code className="raw-el-value">{selector}</code>
        </div>
      )}
      {el.detail && (
        <div className="raw-element-meta">
          <span className="raw-el-label">Detail</span>
          <span className="raw-el-value">{el.detail}</span>
        </div>
      )}
      {bbox && (
        <div className="raw-element-meta">
          <span className="raw-el-label">Position</span>
          <span className="raw-el-value raw-el-bbox">
            x:{Math.round(bbox.x)} y:{Math.round(bbox.y)}&ensp;
            {Math.round(bbox.width)}&times;{Math.round(bbox.height)}px
          </span>
        </div>
      )}
    </div>
  )
}

function RuleRow({ rule }) {
  const [open, setOpen] = useState(false)
  const color = STATUS_COLOR[rule.status] || '#64748b'
  const hasElements = rule.elements && rule.elements.length > 0
  const firstHtml = hasElements && (rule.elements[0]?.html || rule.elements[0]?.snippet)

  return (
    <div className="raw-rule">
      <div
        className="raw-rule-header"
        onClick={() => hasElements && setOpen(o => !o)}
        style={{ cursor: hasElements ? 'pointer' : 'default' }}
      >
        <span className="raw-rule-id">{rule.ruleId}</span>
        {rule.impact && <span className={`impact-pill impact-${rule.impact}`}>{rule.impact}</span>}
        <span className="raw-rule-status" style={{ color, borderColor: color }}>{rule.status}</span>
        {hasElements && (
          <span className="raw-rule-count">{rule.elements.length} element{rule.elements.length !== 1 ? 's' : ''}</span>
        )}
        <span className="raw-rule-reason">{rule.reason}</span>
        {hasElements && <span className="expand-icon" style={{ marginLeft: 'auto' }}>{open ? '▲' : '▼'}</span>}
      </div>

      {firstHtml && (
        <div className="raw-rule-snippet-row">
          <code className="raw-rule-snippet">{firstHtml}</code>
        </div>
      )}

      {open && hasElements && (
        <div className="raw-elements">
          {rule.elements.slice(0, 20).map((el, i) => (
            <ElementCard key={i} el={el} />
          ))}
          {rule.elements.length > 20 && (
            <div className="raw-element-more">…and {rule.elements.length - 20} more</div>
          )}
        </div>
      )}
    </div>
  )
}

function ScEntry({ entry }) {
  const [open, setOpen] = useState(false)
  const statuses = entry.rules.map(r => r.status)
  const topStatus = statuses.includes('fail') ? 'fail'
    : statuses.includes('incomplete') || statuses.includes('needs_review') ? 'needs_review'
    : statuses.includes('pass') ? 'pass'
    : statuses[0] || 'not_checked'
  const color = STATUS_COLOR[topStatus] || '#64748b'

  return (
    <div className="raw-sc-entry">
      <div className="raw-sc-header" onClick={() => setOpen(o => !o)}>
        <span className="raw-sc-id">SC {entry.successCriteriaId}</span>
        <span className="raw-sc-status" style={{ color, borderColor: color }}>{topStatus}</span>
        <span className="raw-sc-rule-count">{entry.rules.length} rule{entry.rules.length !== 1 ? 's' : ''}</span>
        <span className="expand-icon" style={{ marginLeft: 'auto' }}>{open ? '▲' : '▼'}</span>
      </div>
      {open && (
        <div className="raw-sc-rules">
          {entry.rules.map((r, i) => <RuleRow key={i} rule={r} />)}
        </div>
      )}
    </div>
  )
}

export default function RawApiPage() {
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState(null)
  const [result, setResult]             = useState(null)
  const [view, setView]                 = useState('structured') // 'structured' | 'json'
  const [copied, setCopied]             = useState(false)
  const [lastUrl, setLastUrl]           = useState(null)
  const [lastLang, setLastLang]         = useState('en')
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError]   = useState(null)

  async function handleSubmit({ url, lang }) {
    setLoading(true)
    setError(null)
    setResult(null)
    setLastUrl(url)
    setLastLang(lang || 'en')
    setReportError(null)
    try {
      const data = await analyseUrlRaw(url, lang)
      setResult(data)
    } catch (err) {
      setError(err.message || 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleOpenReport() {
    if (!lastUrl) return
    setReportLoading(true)
    setReportError(null)
    try {
      const html = await fetchReport(lastUrl, lastLang)
      const blob = new Blob([html], { type: 'text/html' })
      const url  = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener')
      setTimeout(() => URL.revokeObjectURL(url), 10000)
    } catch (err) {
      setReportError(err.message || 'Report generation failed')
    } finally {
      setReportLoading(false)
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(JSON.stringify(result, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const totalRules = result ? result.results.reduce((s, e) => s + e.rules.length, 0) : 0
  const failCount  = result ? result.results.flatMap(e => e.rules).filter(r => r.status === 'fail').length : 0
  const passCount  = result ? result.results.flatMap(e => e.rules).filter(r => r.status === 'pass').length : 0

  return (
    <div>
      <UrlForm onSubmit={handleSubmit} loading={loading} hideWcagVersion />

      {error && <div className="error-banner">Error: {error}</div>}

      {loading && (
        <div className="loading">
          <div className="spinner" />
          <div>Running raw analysis — this may take 30–60 seconds&hellip;</div>
        </div>
      )}

      {result && (
        <>
          <div className="meta-strip">
            <span>URL: <strong>{result.url}</strong></span>
            <span>{result.results.length} SC entries · {totalRules} rules · {failCount} fail · {passCount} pass</span>
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

          <div className="raw-toolbar">
            <div className="raw-view-toggle">
              <button
                className={`raw-toggle-btn ${view === 'structured' ? 'active' : ''}`}
                onClick={() => setView('structured')}
              >Structured</button>
              <button
                className={`raw-toggle-btn ${view === 'json' ? 'active' : ''}`}
                onClick={() => setView('json')}
              >JSON</button>
            </div>
            <button className="raw-copy-btn" onClick={handleCopy}>
              {copied ? '✓ Copied' : 'Copy JSON'}
            </button>
          </div>

          {view === 'structured' && (
            <div className="raw-sc-list">
              {result.results.map((entry, i) => (
                <ScEntry key={i} entry={entry} />
              ))}
            </div>
          )}

          {view === 'json' && (
            <pre className="raw-json-block">
              {JSON.stringify(result, null, 2)}
            </pre>
          )}
        </>
      )}
    </div>
  )
}
