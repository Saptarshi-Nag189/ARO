export default function HypothesisCard({ hypothesis: h, index }) {
  const conf = h.confidence ?? 0
  const supporting = h.supporting_claim_ids?.length ?? 0
  const opposing = h.opposing_claim_ids?.length ?? 0

  const barColor = conf > 0.7 ? 'var(--accent-emerald)' :
    conf > 0.4 ? 'var(--accent-amber)' : 'var(--accent-rose)'

  return (
    <div className="hypothesis-card" style={{ animationDelay: `${index * 0.06}s` }}>
      <div className="hypothesis-id">{h.id}</div>
      <div className="hypothesis-statement">{h.statement}</div>
      <div className="hypothesis-bar-container">
        <div className="hypothesis-bar-track">
          <div
            className="hypothesis-bar-fill"
            style={{ width: `${conf * 100}%`, background: barColor }}
          />
        </div>
        <div className="hypothesis-bar-value" style={{ color: barColor }}>
          {(conf * 100).toFixed(1)}%
        </div>
      </div>
      <div className="hypothesis-claims">
        <span style={{ color: 'var(--accent-emerald)' }}>▲ {supporting} supporting</span>
        {opposing > 0 && <span style={{ color: 'var(--accent-rose)' }}>▼ {opposing} opposing</span>}
      </div>
    </div>
  )
}
