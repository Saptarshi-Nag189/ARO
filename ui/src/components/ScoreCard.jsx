import { useEffect, useRef } from 'react'

export default function ScoreCard({ label, value, color }) {
  const circumference = 2 * Math.PI * 30 // radius = 30
  const offset = circumference - (Math.min(value, 1) * circumference)
  const displayValue = (value * 100).toFixed(1)

  return (
    <div className="score-card">
      <div className="gauge-ring">
        <svg viewBox="0 0 72 72">
          <circle className="track" cx="36" cy="36" r="30" />
          <circle
            className="fill"
            cx="36" cy="36" r="30"
            stroke={color}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="gauge-value" style={{ color }}>{displayValue}%</div>
      </div>
      <div className="score-card-info">
        <h3>{label}</h3>
        <div className="label">{
          label === 'Hypothesis Confidence' ? (value > 0.7 ? 'Strong' : value > 0.4 ? 'Moderate' : 'Weak') :
          label === 'Epistemic Risk' ? (value < 0.25 ? 'Low Risk' : value < 0.5 ? 'Moderate' : 'High Risk') :
          (value > 0.5 ? 'Novel' : 'Standard')
        }</div>
      </div>
    </div>
  )
}
