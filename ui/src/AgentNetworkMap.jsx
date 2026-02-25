import { useEffect, useRef } from 'react'

const Icon = ({ name, className = '' }) => <span className={`material-symbols-outlined ${className}`}>{name}</span>

const AGENT_NODES = [
  { id: 'planner', label: 'The Architect', icon: 'architecture', color: 'cyan', pos: { x: 25, y: 25 }, status: 'PLANNING' },
  { id: 'research', label: 'Researcher', icon: 'travel_explore', color: 'blue', pos: { x: 75, y: 25 }, status: 'FETCHING' },
  { id: 'claim_extraction', label: 'Fact Checker', icon: 'fact_check', color: 'emerald', pos: { x: 75, y: 50 }, status: 'VERIFYING' },
  { id: 'skeptic', label: 'The Skeptic', icon: 'psychology_alt', color: 'rose', pos: { x: 50, y: 75 }, status: 'CRITIQUING' },
  { id: 'synthesis', label: 'Synthesizer', icon: 'alt_route', color: 'purple', pos: { x: 25, y: 50 }, status: 'MERGING' },
  { id: 'reflection', label: 'Reflector', icon: 'self_improvement', color: 'amber', pos: { x: 50, y: 25 }, status: 'EVALUATING' },
]

const COLOR_MAP = {
  cyan: { border: 'border-cyan-400/50', bg: 'bg-cyan-500/10', text: 'text-cyan-400', glow: '0 0 25px rgba(6,182,212,0.3)', dot: 'bg-cyan-400', shadow: 'shadow-cyan-400/50' },
  blue: { border: 'border-blue-400/50', bg: 'bg-blue-500/10', text: 'text-blue-400', glow: '0 0 25px rgba(59,130,246,0.3)', dot: 'bg-blue-400', shadow: 'shadow-blue-400/50' },
  emerald: { border: 'border-emerald-400/50', bg: 'bg-emerald-500/10', text: 'text-emerald-400', glow: '0 0 25px rgba(16,185,129,0.3)', dot: 'bg-emerald-400', shadow: 'shadow-emerald-400/50' },
  rose: { border: 'border-rose-500/50', bg: 'bg-rose-500/10', text: 'text-rose-400', glow: '0 0 25px rgba(244,63,94,0.3)', dot: 'bg-rose-400', shadow: 'shadow-rose-400/50' },
  purple: { border: 'border-purple-400/50', bg: 'bg-purple-500/10', text: 'text-purple-400', glow: '0 0 25px rgba(168,85,247,0.3)', dot: 'bg-purple-400', shadow: 'shadow-purple-400/50' },
  amber: { border: 'border-amber-400/50', bg: 'bg-amber-500/10', text: 'text-amber-400', glow: '0 0 25px rgba(251,191,36,0.3)', dot: 'bg-amber-400', shadow: 'shadow-amber-400/50' },
}

export default function AgentNetworkMap({ agentStates, report, isRunning }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr; canvas.height = rect.height * dpr; ctx.scale(dpr, dpr)
    const w = rect.width, h = rect.height
    ctx.clearRect(0, 0, w, h)

    // Draw grid
    ctx.strokeStyle = 'rgba(31,41,55,0.3)'; ctx.lineWidth = 1
    for (let x = 0; x < w; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke() }
    for (let y = 0; y < h; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke() }

    // Center orchestrator
    const cx = w / 2, cy = h / 2
    // Draw connections to center
    AGENT_NODES.forEach(node => {
      const nx = (node.pos.x / 100) * w, ny = (node.pos.y / 100) * h
      const grad = ctx.createLinearGradient(cx, cy, nx, ny)
      const isActive = agentStates[node.id] === 'active'
      grad.addColorStop(0, 'rgba(6,182,212,0)')
      grad.addColorStop(0.5, isActive ? 'rgba(6,182,212,0.6)' : 'rgba(6,182,212,0.15)')
      grad.addColorStop(1, 'rgba(6,182,212,0)')
      ctx.beginPath(); ctx.strokeStyle = grad; ctx.lineWidth = isActive ? 2 : 1
      ctx.moveTo(cx, cy); ctx.lineTo(nx, ny); ctx.stroke()
    })

    // Draw orchestrator rings
    ctx.beginPath(); ctx.arc(cx, cy, 50, 0, Math.PI * 2); ctx.strokeStyle = 'rgba(131,60,246,0.15)'; ctx.lineWidth = 1; ctx.stroke()
    ctx.beginPath(); ctx.arc(cx, cy, 70, 0, Math.PI * 2); ctx.strokeStyle = 'rgba(131,60,246,0.08)'; ctx.stroke()
  }, [agentStates])

  const stats = report ? [
    { label: 'System Load', value: '42%', icon: 'memory', color: 'text-primary', delta: '↓ 2.4%', deltaColor: 'text-emerald-400' },
    { label: 'Tasks Done', value: report.total_iterations || 0, icon: 'check_circle', color: 'text-emerald-400', delta: '↑ 12%', deltaColor: 'text-emerald-400' },
    { label: 'Token Usage', value: report.total_tokens_used ? `${(report.total_tokens_used / 1000).toFixed(1)}K` : '0', icon: 'token', color: 'text-purple-400' },
    { label: 'Active Alerts', value: '0', icon: 'warning', color: 'text-amber-400', delta: 'Stable', deltaColor: 'text-emerald-400' },
  ] : []

  return (
    <div className="flex h-full gap-6">
      {/* Agent Registry Sidebar */}
      <div className="w-80 flex flex-col border-r border-white/10 -ml-6 -mt-6 -mb-6 bg-black/20">
        <div className="p-5 border-b border-white/10 flex items-center justify-between bg-white/5">
          <h3 className="font-semibold text-white flex items-center gap-2 tracking-wide text-sm uppercase">
            <Icon name="groups" className="text-primary text-xl" /> Agent Registry
          </h3>
          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            {Object.values(agentStates).filter(s => s === 'active').length || AGENT_NODES.length} ACTIVE
          </span>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4">
          {AGENT_NODES.map(node => {
            const c = COLOR_MAP[node.color]
            const isActive = agentStates[node.id] === 'active'
            const isDone = agentStates[node.id] === 'done'
            return (
              <div key={node.id} className={`p-4 rounded-xl bg-slate-800/40 border border-white/5 hover:${c.border} hover:bg-slate-800/60 transition-all cursor-pointer group relative overflow-hidden`}>
                <div className={`absolute inset-0 bg-gradient-to-r from-${node.color}-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity`}></div>
                <div className="flex items-center justify-between mb-3 relative z-10">
                  <div className="flex items-center gap-3">
                    <div className="relative">
                      <div className={`size-2.5 rounded-full ${isActive ? c.dot + ' shadow-lg ' + c.shadow : isDone ? 'bg-emerald-400' : 'bg-slate-600'}`}></div>
                      {isActive && <div className={`absolute inset-0 rounded-full ${c.dot} animate-ping opacity-75`}></div>}
                    </div>
                    <div>
                      <span className="text-sm font-semibold text-white block">{node.label}</span>
                      <span className={`text-[10px] ${c.text} font-mono`}>ID: {node.id.toUpperCase().slice(0, 3)}-{String(AGENT_NODES.indexOf(node)).padStart(2, '0')}</span>
                    </div>
                  </div>
                </div>
                <div className="space-y-2 relative z-10">
                  <div className="flex justify-between items-end text-xs mb-1">
                    <span className="text-slate-400 font-medium">Status</span>
                    <span className={`${c.text} font-bold font-mono text-[10px]`}>{isActive ? 'RUNNING' : isDone ? 'COMPLETE' : 'STANDBY'}</span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-1.5 border border-white/5 overflow-hidden">
                    <div className={`bg-gradient-to-r from-${node.color}-600 to-${node.color}-400 h-full rounded-full transition-all duration-1000`}
                      style={{ width: isActive ? '60%' : isDone ? '100%' : '0%' }} />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Network Visualization */}
      <div className="flex-1 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 blur-[100px] rounded-full pointer-events-none"></div>
        <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-purple-500/5 blur-[100px] rounded-full pointer-events-none"></div>
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />

        {/* Orchestrator center node */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10 flex flex-col items-center gap-4">
          <div className="relative">
            <div className="absolute inset-0 bg-primary blur-[50px] opacity-20 rounded-full"></div>
            <div className="size-32 rounded-full glass-card border border-primary/40 flex items-center justify-center relative overflow-hidden" style={{ boxShadow: '0 0 50px rgba(131,60,246,0.2)' }}>
              <Icon name="hub" className="text-5xl text-white relative z-10 drop-shadow-lg" />
              {isRunning && <div className="absolute inset-2 border-2 border-t-primary border-l-primary/50 border-r-transparent border-b-transparent rounded-full animate-spin"></div>}
            </div>
            <div className="absolute -top-3 -right-3 bg-gradient-to-r from-primary to-blue-600 text-white text-[10px] font-bold px-2.5 py-1 rounded-full border border-white/20 shadow-lg z-20 tracking-widest">CORE</div>
          </div>
          <div className="text-center">
            <h4 className="text-white font-bold text-base tracking-wide">Orchestrator</h4>
            <div className="flex items-center justify-center gap-1.5 mt-0.5">
              <span className={`size-1.5 rounded-full ${isRunning ? 'bg-primary animate-pulse' : 'bg-slate-600'}`}></span>
              <p className="text-primary text-xs font-mono">{isRunning ? 'RELAYING_DATA' : 'IDLE'}</p>
            </div>
          </div>
        </div>

        {/* Agent nodes */}
        {AGENT_NODES.map(node => {
          const c = COLOR_MAP[node.color]
          const isActive = agentStates[node.id] === 'active'
          return (
            <div key={node.id} className="absolute z-10 flex flex-col items-center gap-3"
              style={{ top: `${node.pos.y}%`, left: `${node.pos.x}%`, transform: 'translate(-50%, -50%)' }}>
              <div className="relative hover:scale-105 transition-transform duration-300">
                <div className={`size-16 rounded-full glass-card ${c.border} flex items-center justify-center relative overflow-hidden`} style={{ boxShadow: isActive ? c.glow : 'none' }}>
                  <Icon name={node.icon} className={`text-3xl text-white relative z-10`} />
                </div>
              </div>
              <div className="text-center">
                <h4 className="text-white font-bold text-sm tracking-wide">{node.label}</h4>
                <span className={`${c.bg} ${c.text} text-[10px] font-mono px-2 py-0.5 rounded border ${c.border} mt-1 inline-block`}>
                  {isActive ? node.status : agentStates[node.id] === 'done' ? 'DONE' : 'IDLE'}
                </span>
              </div>
            </div>
          )
        })}

        {/* Bottom stats bar */}
        {report && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 w-full max-w-4xl px-6">
            <div className="grid grid-cols-4 gap-4">
              {stats.map(s => (
                <div key={s.label} className="glass-card p-4 rounded-xl flex items-center gap-4 hover:border-primary/30 transition-colors group">
                  <div className="relative size-10 flex items-center justify-center bg-gradient-to-br from-slate-800 to-black rounded-lg border border-white/10">
                    <Icon name={s.icon} className={`text-xl ${s.color}`} />
                  </div>
                  <div className="flex flex-col">
                    <p className="text-[10px] uppercase text-slate-400 font-bold tracking-wider mb-0.5">{s.label}</p>
                    <div className="flex items-baseline gap-2">
                      <p className="text-xl font-bold text-white tracking-tight">{s.value}</p>
                      {s.delta && <span className={`text-[10px] ${s.deltaColor} font-mono`}>{s.delta}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
