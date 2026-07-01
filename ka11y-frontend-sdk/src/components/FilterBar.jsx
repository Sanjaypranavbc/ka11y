const STATUS_OPTIONS = [
  { value: 'all',            label: 'All',           activeClass: 'active' },
  { value: 'fail',           label: 'Failed',         activeClass: 'active-fail' },
  { value: 'needs_review',   label: 'Needs Review',   activeClass: 'active-review' },
  { value: 'pass',           label: 'Passed',         activeClass: 'active-pass' },
  { value: 'not_applicable', label: 'N/A',            activeClass: 'active-na' },
  { value: 'not_checked',    label: 'Not Checked',    activeClass: 'active-skipped' },
  { value: 'manual_only',    label: 'Manual Only',    activeClass: 'active-manual' },
]

const LEVEL_OPTIONS = [
  { value: 'all', label: 'All Levels' },
  { value: 'A',   label: 'Level A' },
  { value: 'AA',  label: 'Level AA' },
  { value: 'AAA', label: 'Level AAA' },
]

export default function FilterBar({ statusFilter, levelFilter, onStatusChange, onLevelChange }) {
  return (
    <div className="filter-bar">
      <span className="group-label">Status</span>
      {STATUS_OPTIONS.map(opt => (
        <button
          key={opt.value}
          className={`filter-btn ${statusFilter === opt.value ? opt.activeClass : ''}`}
          onClick={() => onStatusChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}

      <div className="divider" />

      <span className="group-label">Level</span>
      {LEVEL_OPTIONS.map(opt => (
        <button
          key={opt.value}
          className={`filter-btn ${levelFilter === opt.value ? 'active' : ''}`}
          onClick={() => onLevelChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
