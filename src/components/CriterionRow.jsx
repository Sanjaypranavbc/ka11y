import { useState } from 'react'

const STATUS_LABELS = {
  fail:           'Fail',
  pass:           'Pass',
  needs_review:   'Needs Review',
  not_checked:    'Not Checked',
  manual_only:    'Manual Only',
  not_applicable: 'N/A',
}

const DOT_CLASS = {
  fail:         'dot-fail',
  pass:         'dot-pass',
  incomplete:   'dot-incomplete',
  needs_review: 'dot-needs_review',
}

export default function CriterionRow({ criterion }) {
  const [expanded, setExpanded] = useState(false)

  const { sc, name, level, principle, status, findings, reason } = criterion
  const hasFindingDetails = findings && findings.length > 0
  const canExpand = hasFindingDetails || status === 'manual_only' || status === 'not_checked'

  return (
    <div className={`criterion-row ${expanded ? 'expanded' : ''}`}>
      <div
        className="criterion-header"
        onClick={() => canExpand && setExpanded(e => !e)}
        role={canExpand ? 'button' : undefined}
        tabIndex={canExpand ? 0 : undefined}
        onKeyDown={e => { if (canExpand && (e.key === 'Enter' || e.key === ' ')) setExpanded(v => !v) }}
        aria-expanded={canExpand ? expanded : undefined}
      >
        <span className="sc-badge">{sc}</span>

        <span className="criterion-name">{name}</span>

        <span className={`level-badge level-${level}`}>{level}</span>

        <span className="principle-tag">{principle}</span>

        <span className={`status-badge status-${status}`}>
          {STATUS_LABELS[status] || status}
        </span>

        {hasFindingDetails && (
          <span className="finding-count">{findings.length} finding{findings.length !== 1 ? 's' : ''}</span>
        )}

        {canExpand && <span className="expand-icon">▼</span>}
      </div>

      {expanded && (
        <div className="findings-panel">
          {status === 'manual_only' && (
            <div className="manual-note">
              ⚠ Cannot be automated — {reason}
            </div>
          )}

          {status === 'not_checked' && (
            <div className="not-checked-note">
              No automated check implemented for this criterion yet.
            </div>
          )}

          {hasFindingDetails && findings.map((f, i) => (
            <FindingItem key={i} finding={f} />
          ))}
        </div>
      )}
    </div>
  )
}

function FindingItem({ finding }) {
  const { ruleId, status, impact, reason, helpUrl, elements } = finding
  const dotClass = DOT_CLASS[status] || 'dot-incomplete'
  const hasElements = Array.isArray(elements) && elements.length > 0
  const [elementsOpen, setElementsOpen] = useState(false)
  const firstHtml = hasElements && (elements[0]?.html || elements[0]?.snippet)

  return (
    <div className="finding-item">
      <div className={`finding-status-dot ${dotClass}`} />
      <span className="finding-rule">{ruleId}</span>
      {impact && <span className={`impact-pill impact-${impact}`}>{impact}</span>}
      <div className="finding-text">
        <div>{reason}</div>

        {firstHtml && (
          <code className="finding-element-snippet">{firstHtml}</code>
        )}

        {hasElements && (
          <div className="finding-elements">
            <button
              className="elements-toggle"
              onClick={() => setElementsOpen(o => !o)}
              aria-expanded={elementsOpen}
            >
              {elementsOpen ? '▲' : '▼'} {elements.length} element{elements.length !== 1 ? 's' : ''} affected
            </button>

            {elementsOpen && (
              <div className="elements-list">
                {elements.map((el, i) => (
                  <ElementDetail key={i} el={el} index={i} />
                ))}
              </div>
            )}
          </div>
        )}

        {helpUrl && (
          <div className="finding-help">
            <a href={helpUrl} target="_blank" rel="noopener noreferrer">Learn more ↗</a>
          </div>
        )}
      </div>
    </div>
  )
}

function ElementDetail({ el, index }) {
  const bbox     = el.bounding_box
  const html     = el.html || el.snippet
  const selector = el.selector
    || (typeof el.target === 'string' ? el.target : null)
    || (Array.isArray(el.target) ? el.target[0] : null)

  return (
    <div className="element-detail">
      <div className="element-index">#{index + 1}</div>
      {html && (
        <div className="element-field">
          <span className="element-label">HTML</span>
          <code className="element-code">{html}</code>
        </div>
      )}
      {selector && (
        <div className="element-field">
          <span className="element-label">Selector</span>
          <code className="element-code">{selector}</code>
        </div>
      )}
      {el.detail && (
        <div className="element-field">
          <span className="element-label">Detail</span>
          <span className="element-bbox">{el.detail}</span>
        </div>
      )}
      {bbox && (
        <div className="element-field">
          <span className="element-label">Position</span>
          <span className="element-bbox">
            x:{Math.round(bbox.x)} y:{Math.round(bbox.y)} &nbsp;
            {Math.round(bbox.width)}&times;{Math.round(bbox.height)}px
          </span>
        </div>
      )}
    </div>
  )
}
