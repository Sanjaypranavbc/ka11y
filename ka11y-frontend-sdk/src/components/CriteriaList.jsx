import CriterionRow from './CriterionRow.jsx'

export default function CriteriaList({ criteria, totalCount }) {
  const isFiltered = criteria.length !== totalCount

  return (
    <div>
      <div className="criteria-count-bar">
        <span className="criteria-count-text">
          {isFiltered
            ? <>Showing <strong>{criteria.length}</strong> of <strong>{totalCount}</strong> criteria</>
            : <><strong>{totalCount}</strong> criteria total</>
          }
        </span>
        {isFiltered && (
          <span className="criteria-count-filtered">({totalCount - criteria.length} hidden by filter)</span>
        )}
      </div>

      {criteria.length === 0 ? (
        <div className="no-results">No criteria match the current filters.</div>
      ) : (
        <div className="criteria-list" role="list">
          {criteria.map(c => (
            <CriterionRow key={c.sc} criterion={c} />
          ))}
        </div>
      )}
    </div>
  )
}
