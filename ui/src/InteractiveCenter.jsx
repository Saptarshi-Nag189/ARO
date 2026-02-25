import { useState, useEffect, useRef } from 'react'

const Icon = ({ name, className = '' }) => <span className={`material-symbols-outlined ${className}`}>{name}</span>

export default function InteractiveCenter({ agentStates, progressMsg, currentIteration, isRunning, objective }) {
  const [logs, setLogs] = useState([])
  const [userInput, setUserInput] = useState('')
  const [decisionPoint, setDecisionPoint] = useState(null)
  const logEndRef = useRef(null)

  // Track agent events as terminal logs
  useEffect(() => {
    if (!isRunning) return
    const ts = new Date().toLocaleTimeString('en-US', { hour12: false })
    if (progressMsg) {
      setLogs(prev => [...prev.slice(-50), { ts, msg: progressMsg, type: 'system' }])
    }
  }, [progressMsg, isRunning])

  useEffect(() => {
    Object.entries(agentStates).forEach(([agent, state]) => {
      const ts = new Date().toLocaleTimeString('en-US', { hour12: false })
      const agentName = agent.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
      if (state === 'active') {
        setLogs(prev => [...prev.slice(-50), { ts, msg: `${agentName} agent activated.`, type: 'agent', agent: agentName }])
      } else if (state === 'done') {
        setLogs(prev => [...prev.slice(-50), { ts, msg: `${agentName} completed successfully.`, type: 'done', agent: agentName }])
      }
    })
  }, [agentStates])

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [logs])

  const agentColors = {
    Planner: 'text-cyan-400', Research: 'text-blue-400',
    'Claim Extraction': 'text-emerald-400', Skeptic: 'text-rose-400',
    Synthesis: 'text-purple-400', Reflection: 'text-amber-400',
  }

  const activeAgents = Object.entries(agentStates)
    .filter(([, s]) => s === 'active' || s === 'done')
    .map(([id, state]) => ({ id, state, label: id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) }))

  return (
    <div className="flex gap-6 h-full -m-6">
      {/* Left: Terminal Feed */}
      <section className="flex-1 flex flex-col min-w-0 h-full p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-medium flex items-center gap-2">
            <Icon name="terminal" className="text-primary" /> Live Research Feed
          </h2>
          <span className={`text-xs font-mono px-2 py-1 rounded border ${isRunning ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' : 'text-primary/70 bg-primary/10 border-primary/20'}`}>
            STATUS: {isRunning ? 'LIVE' : 'PAUSED'}
          </span>
        </div>

        <div className="flex-1 rounded-xl bg-[#051014] border border-white/10 shadow-2xl overflow-hidden flex flex-col font-mono text-sm relative">
          {/* Terminal header */}
          <div className="bg-white/5 px-4 py-2 border-b border-white/5 flex items-center gap-2">
            <div className="flex gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-red-500/80"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-green-500/80"></div>
            </div>
            <div className="ml-4 text-xs text-slate-500">aro_core_process — interactive_mode</div>
          </div>

          {/* Terminal content */}
          <div className="flex-1 overflow-y-auto p-6 custom-scrollbar text-slate-300 space-y-3">
            {logs.length === 0 && !isRunning && (
              <div className="text-slate-600 py-8 text-center">
                <p>No active research feed.</p>
                <p className="text-xs mt-2">Start a research session to see live agent logs here.</p>
              </div>
            )}
            {logs.map((log, i) => (
              <div key={i} className={`${i < logs.length - 3 ? 'opacity-50' : 'opacity-80'} hover:opacity-100 transition-opacity`}>
                <span className="text-emerald-500 font-semibold">[{log.ts}]</span>{' '}
                {log.type === 'agent' ? (
                  <><span className={`font-bold ${agentColors[log.agent] || 'text-primary'}`}>@{log.agent?.replace(/\s/g, '_')}</span> <span className="text-slate-400">::</span> {log.msg}</>
                ) : log.type === 'done' ? (
                  <><span className="text-emerald-400 font-bold">✓ {log.agent}</span> <span className="text-slate-400">::</span> {log.msg}</>
                ) : (
                  <><span className="text-slate-400">SYSTEM</span> <span className="text-slate-400">::</span> {log.msg}</>
                )}
              </div>
            ))}

            {isRunning && (
              <div className="mt-4 text-primary font-bold flex items-center gap-1">
                <span>Processing</span>
                <span className="inline-block w-2 h-4 bg-primary ml-1 animate-pulse"></span>
              </div>
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      </section>

      {/* Right: Controls Panel */}
      <section className="w-[420px] flex flex-col gap-5 h-full overflow-y-auto p-6 pl-0 custom-scrollbar">
        {/* Manual Input */}
        <div className="glass-card rounded-xl p-5">
          <h3 className="text-xs uppercase tracking-wider text-slate-500 font-bold mb-3 flex items-center gap-2">
            <Icon name="edit_note" className="text-sm" /> Manual Injection
          </h3>
          <div className="relative">
            <textarea
              className="w-full bg-[#051014] border border-white/10 rounded-lg p-3 text-sm text-slate-200 placeholder-slate-600 focus:ring-1 focus:ring-primary focus:border-primary resize-none h-28"
              placeholder="Provide additional context, paste URLs, or set constraints for the next iteration..."
              value={userInput}
              onChange={e => setUserInput(e.target.value)}
            />
            <div className="absolute bottom-2 right-2 text-[10px] text-slate-600 font-mono bg-[#051014] px-1 rounded border border-white/5">CMD + ENTER</div>
          </div>
        </div>

        {/* Active Agents */}
        <div>
          <h3 className="text-xs uppercase tracking-wider text-slate-500 font-bold mb-3 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-primary"></span> Active Agents
          </h3>
          <div className="grid grid-cols-3 gap-3">
            {['Planner', 'Research', 'Claim Extraction', 'Skeptic', 'Synthesis', 'Reflection'].map(name => {
              const id = name.toLowerCase().replace(/\s/g, '_')
              const isActive = agentStates[id] === 'active'
              const isDone = agentStates[id] === 'done'
              const borderColor = isActive ? 'border-primary/30' : isDone ? 'border-emerald-500/30' : 'border-white/5'
              const icons = { Planner: 'architecture', Research: 'travel_explore', 'Claim Extraction': 'fact_check', Skeptic: 'psychology_alt', Synthesis: 'alt_route', Reflection: 'self_improvement' }
              return (
                <div key={name} className={`bg-[#051014] border ${borderColor} rounded-lg p-3 flex flex-col items-center gap-2 relative overflow-hidden group hover:bg-white/5 transition-colors cursor-pointer`}>
                  {isActive && <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></div>}
                  {isDone && <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-emerald-400"></div>}
                  <div className={`w-10 h-10 rounded-full ${isActive ? 'bg-primary/10 text-primary' : isDone ? 'bg-emerald-500/10 text-emerald-400' : 'bg-white/5 text-slate-500'} flex items-center justify-center border ${isActive ? 'border-primary/30' : isDone ? 'border-emerald-500/30' : 'border-white/10'} transition-all`}>
                    <Icon name={icons[name] || 'smart_toy'} className="text-lg" />
                  </div>
                  <div className="text-center">
                    <span className={`text-xs font-bold ${isActive || isDone ? 'text-slate-200' : 'text-slate-500'} block`}>{name.split(' ')[0]}</span>
                    <span className="text-[10px] text-slate-600 uppercase tracking-wide">{isActive ? 'Active' : isDone ? 'Done' : 'Idle'}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Iteration info */}
        <div className="glass-card rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs uppercase tracking-wider text-slate-500 font-bold flex items-center gap-2">
              <Icon name="monitoring" className="text-sm" /> Session Status
            </h3>
            {isRunning && (
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span className="text-[10px] text-emerald-400 font-mono">LIVE</span>
              </span>
            )}
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-slate-400">Objective</span><span className="text-white font-medium text-right max-w-[200px] truncate">{objective || '—'}</span></div>
            <div className="flex justify-between"><span className="text-slate-400">Iteration</span><span className="text-primary font-mono font-bold">{currentIteration || 0}</span></div>
            <div className="flex justify-between"><span className="text-slate-400">Active Agents</span><span className="text-white font-mono font-bold">{Object.values(agentStates).filter(s => s === 'active').length}</span></div>
          </div>
        </div>

        {/* Footer stats */}
        <div className="mt-auto pt-4 border-t border-white/5 flex gap-6 text-[10px] font-mono text-slate-500 flex-wrap">
          <span>Server: <span className="text-emerald-400 font-bold">Local</span></span>
          <span>Status: <span className={isRunning ? 'text-emerald-400 font-bold' : 'text-slate-400'}>
            {isRunning ? 'Active' : 'Idle'}
          </span></span>
          <span className="text-emerald-500/80 flex items-center gap-1"><Icon name="lock" className="text-[10px]" /> Encrypted</span>
        </div>
      </section>
    </div>
  )
}
