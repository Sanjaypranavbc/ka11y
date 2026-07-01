import { useState } from 'react'

const GRADE_META = {
  A: { label: 'Excellent',  color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' },
  B: { label: 'Good',       color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc' },
  C: { label: 'Fair',       color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  D: { label: 'Poor',       color: '#ea580c', bg: '#fff7ed', border: '#fed7aa' },
  F: { label: 'Critical',   color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
}

const GRADE_ROWS = [
  { grade: 'A', label: 'Excellent', range: '≥ 90%',                      note: 'No Level A failures' },
  { grade: 'B', label: 'Good',      range: '75–89%',                     note: 'No Level A failures' },
  { grade: 'C', label: 'Fair',      range: '60–74%',                     note: 'No Level A failures' },
  { grade: 'D', label: 'Poor',      range: '40–59%',                     note: 'No Level A failures' },
  { grade: 'F', label: 'Critical',  range: '< 40% or any Level A fail',  note: '' },
]

export default function SummaryBar({ summary, score, grade, hasLevelAFail, levelAFailures = [] }) {
  const [showInfo, setShowInfo] = useState(false)
  const { total, checked, passed, failed, needsReview, notChecked, notApplicable, manualOnly } = summary
  const meta = grade ? GRADE_META[grade] : null

  // When Level A failures force Grade F, keep the ring neutral so it doesn't
  // visually contradict the high numeric score.
  const ringColor  = hasLevelAFail ? '#94a3b8' : (meta ? meta.color : '#6366f1')
  const cardBg     = meta ? meta.bg     : '#fff'
  const cardBorder = meta ? meta.border : '#e2e8f0'

  return (
    <div className="summary-section">

      {/* ── Score card ── */}
      {score !== null && meta && (
        <div className="score-card" style={{ borderColor: cardBorder, background: cardBg }}>

          {/* Left: numeric pass rate */}
          <div className="score-rate-section">
            <div className="score-ring" style={{ borderColor: ringColor }}>
              <span className="score-number" style={{ color: ringColor }}>{score}</span>
              <span className="score-pct"    style={{ color: ringColor }}>%</span>
            </div>
            <div className="score-ring-label">auto pass rate</div>
          </div>

          <div className="score-card-divider" />

          {/* Right: conformance grade */}
          <div className="score-info">
            <div className="score-grade-row">
              <div className="score-conformance-label">WCAG Conformance</div>
              <button
                className="score-info-btn"
                onClick={() => setShowInfo(v => !v)}
                aria-expanded={showInfo}
                aria-label="Show grade and score details"
                title="How is the score calculated?"
              >
                ⓘ
              </button>
            </div>

            <div className="score-grade" style={{ color: meta.color }}>
              Grade <strong>{grade}</strong>
              <span className="score-grade-label"> — {meta.label}</span>
            </div>

            {hasLevelAFail && (
              <div className="score-level-a-warning">
                <div className="score-level-a-title">
                  Level A failures — grade is F regardless of pass rate
                </div>
                <ul className="score-level-a-list">
                  {levelAFailures.map(c => (
                    <li key={c.sc}>
                      <span className="level-a-sc">SC {c.sc}</span>
                      <span className="level-a-name">{c.name}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="score-formula">
              {passed} passed ÷ ({passed} + {failed} failed + {needsReview} review) = {score}%
            </div>
          </div>
        </div>
      )}

      {/* ── Score details panel ── */}
      {showInfo && (
        <div className="score-details-panel">
          <div className="score-details-header">
            <span>How is the score calculated?</span>
            <button
              className="score-details-close"
              onClick={() => setShowInfo(false)}
              aria-label="Close details"
            >✕</button>
          </div>

          <div className="score-details-body">
            <div className="score-details-section">
              <h4>Two separate metrics</h4>
              <p>
                <strong>Auto pass rate</strong> (the number in the circle) = how many of the
                automatically-checked criteria did not trigger a violation.
                Formula: <strong>Passed ÷ (Passed + Failed + Needs Review) × 100</strong>.
              </p>
              <p>
                <strong>Conformance grade</strong> (the letter) = whether the site can claim any
                level of WCAG conformance. WCAG is all-or-nothing — failing even one Level A
                criterion means no conformance can be claimed, so the grade is capped at F
                regardless of the pass rate.
              </p>
              <p>
                Criteria marked <em>N/A</em>, <em>Not Checked</em>, and <em>Manual Only</em> are
                excluded from the pass-rate denominator.
              </p>
            </div>

            <div className="score-details-section">
              <h4>Conformance grade thresholds</h4>
              <table className="score-details-table">
                <thead>
                  <tr><th>Grade</th><th>Label</th><th>Pass rate</th><th>Condition</th></tr>
                </thead>
                <tbody>
                  {GRADE_ROWS.map(r => (
                    <tr key={r.grade} className={grade === r.grade ? 'current-grade-row' : ''}>
                      <td><span style={{ color: GRADE_META[r.grade].color, fontWeight: 700 }}>{r.grade}</span></td>
                      <td>{r.label}</td>
                      <td>{r.range}</td>
                      <td>{r.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="score-details-section">
              <h4>Status definitions</h4>
              <ul className="score-details-list">
                <li><span className="status-badge status-fail">Fail</span> — Automated check found a violation</li>
                <li><span className="status-badge status-needs_review">Needs Review</span> — Potential issue requiring human verification</li>
                <li><span className="status-badge status-pass">Pass</span> — Automated check found no violation</li>
                <li><span className="status-badge status-not_applicable">N/A</span> — No relevant content on this page (excluded from pass rate)</li>
                <li><span className="status-badge status-not_checked">Not Checked</span> — No automated rule implemented yet (excluded from pass rate)</li>
                <li><span className="status-badge status-manual_only">Manual Only</span> — Cannot be automated; requires expert review (excluded from pass rate)</li>
              </ul>
            </div>

            <div className="score-details-section score-details-note">
              Automated tools detect approximately 30–40% of accessibility issues.
              A high pass rate does not guarantee full accessibility — manual testing is always recommended.
            </div>
          </div>
        </div>
      )}

      {/* ── Summary cards ── */}
      <div className="summary-bar">
        <div className="summary-card total">
          <div className="count">{total}</div>
          <div className="label">Total Criteria</div>
        </div>
        <div className="summary-card checked">
          <div className="count">{checked}</div>
          <div className="label">Checked</div>
        </div>
        <div className="summary-card fail">
          <div className="count">{failed}</div>
          <div className="label">Failed</div>
        </div>
        <div className="summary-card review">
          <div className="count">{needsReview}</div>
          <div className="label">Needs Review</div>
        </div>
        <div className="summary-card pass">
          <div className="count">{passed}</div>
          <div className="label">Passed</div>
        </div>
        <div className="summary-card na">
          <div className="count">{notApplicable ?? 0}</div>
          <div className="label">N/A</div>
        </div>
        <div className="summary-card skipped">
          <div className="count">{notChecked}</div>
          <div className="label">Not Checked</div>
        </div>
        <div className="summary-card manual">
          <div className="count">{manualOnly}</div>
          <div className="label">Manual Only</div>
        </div>
      </div>
    </div>
  )
}
