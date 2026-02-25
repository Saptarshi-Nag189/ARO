import { useRef, useEffect } from 'react'

export default function IterationChart({ metrics }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !metrics?.length) return

    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)

    const w = rect.width
    const h = rect.height
    const pad = { top: 20, right: 32, bottom: 36, left: 48 }
    const chartW = w - pad.left - pad.right
    const chartH = h - pad.top - pad.bottom

    ctx.clearRect(0, 0, w, h)

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.04)'
    ctx.lineWidth = 1
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (chartH / 4) * i
      ctx.beginPath()
      ctx.moveTo(pad.left, y)
      ctx.lineTo(w - pad.right, y)
      ctx.stroke()
    }

    // Y-axis labels
    ctx.font = '11px JetBrains Mono, monospace'
    ctx.fillStyle = '#64748b'
    ctx.textAlign = 'right'
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (chartH / 4) * i
      ctx.fillText(((4 - i) * 0.25).toFixed(2), pad.left - 8, y + 4)
    }

    // X-axis labels
    ctx.textAlign = 'center'
    metrics.forEach((m, i) => {
      const x = pad.left + (chartW / Math.max(metrics.length - 1, 1)) * i
      ctx.fillText(`Iter ${m.iteration}`, x, h - 8)
    })

    // Draw lines
    const series = [
      { key: 'hypothesis_confidence', color: '#3b82f6', label: 'Confidence' },
      { key: 'epistemic_risk', color: '#f43f5e', label: 'Risk' },
      { key: 'novelty_score', color: '#06b6d4', label: 'Novelty' },
    ]

    series.forEach(({ key, color }) => {
      ctx.beginPath()
      ctx.strokeStyle = color
      ctx.lineWidth = 2.5
      ctx.lineJoin = 'round'
      ctx.lineCap = 'round'

      metrics.forEach((m, i) => {
        const x = pad.left + (chartW / Math.max(metrics.length - 1, 1)) * i
        const y = pad.top + chartH - (m[key] ?? 0) * chartH
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke()

      // Dots
      metrics.forEach((m, i) => {
        const x = pad.left + (chartW / Math.max(metrics.length - 1, 1)) * i
        const y = pad.top + chartH - (m[key] ?? 0) * chartH
        ctx.beginPath()
        ctx.arc(x, y, 4, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
        ctx.beginPath()
        ctx.arc(x, y, 2, 0, Math.PI * 2)
        ctx.fillStyle = '#0a0e1a'
        ctx.fill()
      })
    })
  }, [metrics])

  return (
    <div className="chart-container">
      <canvas ref={canvasRef} className="chart-canvas" />
      <div className="chart-legend">
        <div className="chart-legend-item">
          <span className="chart-legend-dot" style={{ background: '#3b82f6' }} />
          Confidence
        </div>
        <div className="chart-legend-item">
          <span className="chart-legend-dot" style={{ background: '#f43f5e' }} />
          Risk
        </div>
        <div className="chart-legend-item">
          <span className="chart-legend-dot" style={{ background: '#06b6d4' }} />
          Novelty
        </div>
      </div>
    </div>
  )
}
