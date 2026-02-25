export default function GapCard({ gap: g, index }) {
  const sev = g.severity ?? 0
  const sevLabel = sev >= 0.8 ? 'High' : sev >= 0.5 ? 'Medium' : 'Low'
  const sevBg = sev >= 0.8 ? 'rgba(244,63,94,0.12)' : sev >= 0.5 ? 'rgba(245,158,11,0.12)' : 'rgba(59,130,246,0.12)'
  const sevColor = sev >= 0.8 ? 'var(--accent-rose)' : sev >= 0.5 ? 'var(--accent-amber)' : 'var(--accent-blue)'

  return (
    <div className="gap-card" style={{ animationDelay: `${index * 0.06}s` }}>
      <div className="gap-severity" style={{ background: sevBg, color: sevColor }}>
        ● {sevLabel} Severity ({(sev * 100).toFixed(0)}%)
      </div>
      <div className="gap-desc">{g.description}</div>
      {g.suggested_queries?.length > 0 && (
        <div className="gap-queries">
          {g.suggested_queries.map((q, i) => (
            <span key={i} className="gap-query-tag">{q}</span>
          ))}
        </div>
      )}
    </div>
  )
}
