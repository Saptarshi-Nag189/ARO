import { useState } from 'react'

export default function ClaimsTable({ claims }) {
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? claims : claims.slice(0, 10)

  return (
    <div className="claims-table-wrap">
      <table className="claims-table">
        <thead>
          <tr>
            <th style={{ width: '25%' }}>Subject</th>
            <th style={{ width: '12%' }}>Relation</th>
            <th style={{ width: '35%' }}>Object</th>
            <th style={{ width: '13%' }}>Confidence</th>
            <th style={{ width: '15%' }}>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((c, i) => {
            const conf = c.confidence_estimate ?? 0
            const pillBg = conf >= 0.9 ? 'rgba(16,185,129,0.15)' :
              conf >= 0.7 ? 'rgba(59,130,246,0.15)' : 'rgba(245,158,11,0.15)'
            const pillColor = conf >= 0.9 ? 'var(--accent-emerald)' :
              conf >= 0.7 ? 'var(--accent-blue)' : 'var(--accent-amber)'

            return (
              <tr key={c.id || i}>
                <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{c.subject}</td>
                <td><em>{c.relation}</em></td>
                <td>{c.object}</td>
                <td>
                  <span className="confidence-pill" style={{ background: pillBg, color: pillColor }}>
                    {(conf * 100).toFixed(0)}%
                  </span>
                </td>
                <td style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                  ×{c.evidence_count ?? 1}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {claims.length > 10 && (
        <div style={{
          textAlign: 'center', padding: '12px',
          borderTop: '1px solid var(--border-subtle)',
        }}>
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              background: 'none', border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-full)', padding: '6px 16px',
              color: 'var(--accent-blue)', cursor: 'pointer', fontSize: 12,
              fontFamily: 'inherit', fontWeight: 500,
            }}
          >
            {expanded ? 'Show Less' : `Show All ${claims.length} Claims`}
          </button>
        </div>
      )}
    </div>
  )
}
