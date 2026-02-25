import { useState, useEffect, useRef, useCallback } from 'react'
import AgentNetworkMap from './AgentNetworkMap'
import HypothesisDeepDive from './HypothesisDeepDive'
import ReportExport from './ReportExport'
import KnowledgeBase from './KnowledgeBase'
import InteractiveCenter from './InteractiveCenter'

const AGENTS = ['planner', 'research', 'claim_extraction', 'skeptic', 'synthesis', 'reflection']
const Icon = ({ name, className = '' }) => <span className={`material-symbols-outlined ${className}`}>{name}</span>

export default function App() {
  const [sessions, setSessions] = useState([])
  const [activeReport, setActiveReport] = useState(null)
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [objective, setObjective] = useState('')
  const [mode, setMode] = useState('autonomous')
  const [maxIterations, setMaxIterations] = useState(10)
  const [agentStates, setAgentStates] = useState({})
  const [currentIteration, setCurrentIteration] = useState(0)
  const [progressMsg, setProgressMsg] = useState('')
  const [error, setError] = useState(null)
  const [activeNav, setActiveNav] = useState('dashboard')
  const [searchQuery, setSearchQuery] = useState('')
  const [deepDiveHypothesis, setDeepDiveHypothesis] = useState(null)
  const [showExport, setShowExport] = useState(false)
  const [cachedReports, setCachedReports] = useState({})
  const [viewingLive, setViewingLive] = useState(true)
  const [inputExpanded, setInputExpanded] = useState(false)
  const eventSourceRef = useRef(null)

  useEffect(() => {
    fetch('/api/sessions').then(r => r.json()).then(setSessions).catch(() => {})
  }, [])

  const loadReport = useCallback((sessionId) => {
    if (isRunning) setViewingLive(false)
    setActiveSessionId(sessionId)
    setActiveNav('dashboard')
    setError(null)
    setDeepDiveHypothesis(null)
    fetch(`/api/report/${sessionId}`)
      .then(r => r.json())
      .then(data => { if (data.error) { setError(data.error); return }; setActiveReport(data); setCachedReports(prev => ({ ...prev, [sessionId]: data })) })
      .catch(e => setError(e.message))
  }, [isRunning])

  const startResearch = useCallback(() => {
    if (!objective.trim() || isRunning) return
    setIsRunning(true); setActiveReport(null); setError(null)
    setAgentStates({}); setCurrentIteration(0); setProgressMsg('Initializing agents...')
    setViewingLive(true); setInputExpanded(false)

    fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objective, mode, max_iterations: maxIterations }),
    })
      .then(r => r.json())
      .then(({ session_id }) => {
        setActiveSessionId(session_id)
        if (eventSourceRef.current) eventSourceRef.current.close()
        const es = new EventSource(`/api/stream/${session_id}`)
        eventSourceRef.current = es
        es.onmessage = (e) => {
          const data = JSON.parse(e.data)
          if (data.type === 'agent_start') {
            setAgentStates(prev => ({ ...prev, [data.agent]: 'active' }))
            setCurrentIteration(data.iteration || 0)
            setProgressMsg(`Running ${data.agent.replace(/_/g, ' ')}...`)
          }
          if (data.type === 'agent_done') setAgentStates(prev => ({ ...prev, [data.agent]: 'done' }))
          if (data.type === 'iteration_complete') {
            setCurrentIteration(data.iteration); setProgressMsg(`Iteration ${data.iteration} complete`); setAgentStates({})
          }
          if (data.type === 'complete') { setActiveReport(data.report); setIsRunning(false); setViewingLive(true); es.close(); eventSourceRef.current = null; fetch('/api/sessions').then(r => r.json()).then(setSessions).catch(() => {}) }
          if (data.type === 'error') { setError(data.message); setIsRunning(false); es.close(); eventSourceRef.current = null }
          if (data.type === 'done') { setIsRunning(false); es.close(); eventSourceRef.current = null; fetch('/api/sessions').then(r => r.json()).then(setSessions).catch(() => {}) }
        }
        es.onerror = () => { setIsRunning(false); es.close(); eventSourceRef.current = null }
      })
      .catch(e => { setError(e.message); setIsRunning(false) })
  }, [objective, mode, maxIterations, isRunning])

  const filteredSessions = sessions.filter(s =>
    !searchQuery || s.objective?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const r = activeReport

  return (
    <div className="flex h-screen w-full">
      {/* ── Sidebar ── */}
      <aside className="w-[280px] bg-sidebar-dark border-r border-primary/10 flex flex-col shrink-0">
        <div className="p-6 flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <div className="size-10 rounded-lg bg-gradient-to-br from-primary to-cyan-500 flex items-center justify-center text-white shadow-lg shadow-primary/20">
              <Icon name="query_stats" className="font-bold" />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-white">ARO</h1>
          </div>
          <p className="text-[10px] uppercase tracking-widest text-primary font-bold opacity-80 pl-1">
            Autonomous Research Operator
          </p>
        </div>

        <div className="px-4 pb-4">
          <div className="relative">
            <Icon name="search" className="absolute left-2.5 top-2 text-slate-500 text-sm" />
            <input
              className="w-full bg-white/5 border border-white/10 rounded-lg py-1.5 pl-8 pr-3 text-xs text-slate-300 focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-slate-600 transition-all"
              placeholder="Search sessions..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        <nav className="flex-1 px-4 overflow-y-auto custom-scrollbar">
          <div className="mb-6">
            <div className="flex items-center gap-2 px-3 mb-2 text-[10px] font-bold text-slate-500 uppercase tracking-widest">Main Menu</div>
            <div className="space-y-1">
              {[
                { id: 'dashboard', icon: 'dashboard', label: 'Dashboard' },
                { id: 'network', icon: 'hub', label: 'Network Map' },
                { id: 'knowledge', icon: 'public', label: 'Knowledge Base' },
                { id: 'claims', icon: 'link', label: 'Key Claims' },
                { id: 'gaps', icon: 'error', label: 'Knowledge Gaps' },
                { id: 'interactive', icon: 'terminal', label: 'Live Terminal' },
                { id: 'progress', icon: 'monitoring', label: 'Progress' },
                { id: 'reports', icon: 'description', label: 'Reports', badge: r ? 'New' : null },
              ].map(item => (
                <a key={item.id}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-all cursor-pointer ${
                    activeNav === item.id
                      ? 'bg-primary/20 text-primary border border-primary/20'
                      : 'text-slate-400 hover:bg-white/5 hover:text-slate-200 border border-transparent'
                  }`}
                  onClick={() => setActiveNav(item.id)}
                >
                  <Icon name={item.icon} className="text-xl" />
                  <span className="text-sm font-medium">{item.label}</span>
                  {item.badge && <span className="ml-auto text-[10px] bg-white/10 px-1.5 py-0.5 rounded text-slate-300">{item.badge}</span>}
                </a>
              ))}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between px-3 mb-2 text-[10px] font-bold text-slate-500 uppercase tracking-widest">
              <span>Recent Sessions</span>
            </div>
            <div className="space-y-1">
              {filteredSessions.length === 0 && (
                <p className="px-3 py-2 text-xs text-slate-600">No sessions yet</p>
              )}
              {filteredSessions.map(s => (
                <div key={s.session_id}
                  className={`px-3 py-2 rounded-lg mb-1 cursor-pointer transition-all ${
                    activeSessionId === s.session_id
                      ? 'border-l-2 border-primary bg-primary/10'
                      : 'hover:bg-white/5'
                  }`}
                  onClick={() => loadReport(s.session_id)}
                >
                  <p className="text-xs font-medium text-white truncate">{s.objective}</p>
                  <p className="text-[10px] text-slate-500">
                    {s.iterations} iter · {(s.time / 60).toFixed(1)}m
                  </p>
                </div>
              ))}
            </div>
          </div>
        </nav>

        <div className="p-4 border-t border-white/5">
          <button
            className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary text-white py-2.5 rounded-lg transition-all text-sm font-bold shadow-lg shadow-primary/20"
            onClick={() => { setActiveReport(null); setActiveSessionId(null); setActiveNav('dashboard'); setObjective('') }}
          >
            <Icon name="add_circle" className="text-sm" /> New Research
          </button>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="flex-1 flex flex-col overflow-hidden relative bg-gradient-to-br from-bg-dark to-[#0f1629]">
        {/* Header bar */}
        {(isRunning || activeReport) && (
          <div className="px-6 py-2 border-b border-white/5 flex items-center justify-between bg-black/20">
            <div className="flex items-center gap-4">
              {isRunning && (
                <span className="flex h-2 w-2 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
              )}
              <span className="text-xs font-bold text-slate-300 uppercase tracking-wider max-w-[400px] truncate block">
                {isRunning ? 'Active: ' : 'Session: '}
                <span className="text-white">{(r?.research_objective || objective || '').slice(0, 80)}{(r?.research_objective || objective || '').length > 80 ? '…' : ''}</span>
              </span>
            </div>
            <div className="flex items-center gap-6 text-[10px] font-mono font-bold uppercase tracking-widest text-slate-500">
              {isRunning && (
                <>
                  <div className="flex items-center gap-2">
                    <Icon name="loop" className="text-sm" /> Iteration: <span className="text-cyan-400">{currentIteration}/{maxIterations}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Icon name="timer" className="text-sm" /> Status: <span className="text-emerald-400">Live</span>
                  </div>
                </>
              )}
              {r && !isRunning && (
                <>
                  <div className="flex items-center gap-2">
                    <Icon name="loop" className="text-sm" /> Iterations: <span className="text-cyan-400">{r.total_iterations}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Icon name="token" className="text-sm" /> Tokens: <span className="text-slate-300">{r.total_tokens_used?.toLocaleString()}</span>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* Input area */}
        <div className="px-6 py-3 border-b border-white/5 bg-sidebar-dark/50 backdrop-blur-md space-y-3">
          <div className="relative">
            <textarea
              className={`w-full bg-card-dark/80 backdrop-blur-sm border border-white/10 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-primary focus:border-transparent resize-none custom-scrollbar placeholder:text-slate-600 transition-all ${inputExpanded ? 'h-[160px]' : 'h-[48px]'}`}
              placeholder="What would you like to research?"
              value={objective}
              onChange={e => setObjective(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startResearch() }}}
              disabled={isRunning}
            />
            {objective.length > 100 && (
              <button onClick={() => setInputExpanded(!inputExpanded)} className="absolute bottom-1.5 right-2 text-[10px] text-slate-500 hover:text-primary transition-colors bg-card-dark/90 px-2 py-0.5 rounded border border-white/5">
                {inputExpanded ? 'Collapse ▲' : 'Expand ▼'}
              </button>
            )}
          </div>
          <div className="flex gap-2 items-center justify-end">
            <div className="flex items-center bg-card-dark border border-white/10 rounded-xl px-1 p-1 h-9">
              {['autonomous', 'innovation', 'interactive'].map(m => (
                <button key={m}
                  className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors capitalize ${
                    mode === m ? 'text-white bg-primary/20' : 'text-slate-400 hover:text-white'
                  }`}
                  onClick={() => setMode(m)}
                  disabled={isRunning}
                >{m === 'autonomous' ? 'Auto' : m === 'innovation' ? 'Innov' : 'Interactive'}</button>
              ))}
            </div>
            <input
              type="number"
              className="w-14 h-9 bg-card-dark border border-white/10 rounded-xl text-center text-xs text-slate-300 focus:ring-1 focus:ring-primary"
              value={maxIterations}
              onChange={e => setMaxIterations(Math.max(1, parseInt(e.target.value) || 1))}
              min={1} max={50}
              title="Max Iterations"
              disabled={isRunning}
            />
            <button
              className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold h-9 px-5 rounded-xl text-xs flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20 transition-all"
              onClick={startResearch}
              disabled={isRunning || !objective.trim()}
            >
              {isRunning ? <><span className="spinner" /> Running...</> : <><Icon name="play_arrow" className="text-base" /> Run</>}
            </button>
          </div>
        </div>

        {/* Back to Live Research banner */}
        {isRunning && !viewingLive && (
          <div className="px-6 py-2 bg-gradient-to-r from-primary/20 to-emerald-500/10 border-b border-primary/20 flex items-center justify-between cursor-pointer hover:from-primary/30 hover:to-emerald-500/20 transition-all"
            onClick={() => { setViewingLive(true); setActiveReport(null); setActiveNav('dashboard') }}>
            <div className="flex items-center gap-3">
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span className="text-xs font-bold text-emerald-300">Research in progress — "{objective.slice(0, 50)}{objective.length > 50 ? '…' : ''}"</span>
              <span className="text-xs text-slate-400 font-mono">Iteration {currentIteration}/{maxIterations}</span>
            </div>
            <span className="text-xs font-bold text-primary hover:text-white flex items-center gap-1 transition-colors">
              <Icon name="arrow_back" className="text-sm" /> Return to live view
            </span>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-6">
          {error && (
            <div className="glass-card rounded-xl p-4 border-l-4 border-l-rose-500 flex items-center gap-3">
              <Icon name="warning" className="text-rose-400" />
              <p className="text-sm text-rose-300">{error}</p>
            </div>
          )}

          {/* Live Progress — show when running AND viewing live */}
          {isRunning && viewingLive && !activeReport && (
            <div className="flex flex-col items-center justify-center py-20 space-y-8">
              <div className="flex items-center gap-3 flex-wrap justify-center">
                {AGENTS.map((agent, i) => (
                  <span key={agent} className="flex items-center gap-2">
                    {i > 0 && <Icon name="arrow_forward" className="text-slate-700 text-sm" />}
                    <span className={`px-4 py-2 rounded-full text-xs font-bold border transition-all ${
                      agentStates[agent] === 'active'
                        ? 'bg-primary/20 border-primary text-primary shadow-lg shadow-primary/20 animate-pulse-slow'
                        : agentStates[agent] === 'done'
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                        : 'bg-card-dark border-white/10 text-slate-600'
                    }`}>
                      {agent.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    </span>
                  </span>
                ))}
              </div>
              <p className="text-sm text-slate-400">{progressMsg}</p>
              {currentIteration > 0 && <p className="text-xs text-slate-600 font-mono">Iteration {currentIteration}</p>}
            </div>
          )}

          {/* Welcome */}
          {!isRunning && !activeReport && !error && (
            <div className="flex flex-col items-center justify-center py-24 space-y-6">
              <div className="size-20 rounded-2xl bg-gradient-to-br from-primary to-cyan-500 flex items-center justify-center shadow-2xl shadow-primary/30">
                <Icon name="query_stats" className="text-white text-4xl" />
              </div>
              <h2 className="text-2xl font-bold text-white">Autonomous Research Engine</h2>
              <p className="text-slate-400 max-w-md text-center leading-relaxed">
                Enter a research objective above. ARO deploys 7 specialized AI agents to autonomously
                research, extract claims, challenge findings, and synthesize hypotheses with real-time
                epistemic confidence tracking.
              </p>
            </div>
          )}

          {/* Deep Dive View */}
          {deepDiveHypothesis && (
            <HypothesisDeepDive hypothesis={deepDiveHypothesis} report={r} onBack={() => setDeepDiveHypothesis(null)} />
          )}

          {/* Dashboard */}
          {r && activeNav === 'dashboard' && !deepDiveHypothesis && (
            <>
              <ScoreCards report={r} />
              {r.conclusion && <ConclusionCard conclusion={r.conclusion} report={r} />}
              <HypothesesSection hypotheses={r.hypotheses} onDeepDive={setDeepDiveHypothesis} />
              <ClaimsSection claims={r.key_claims} />
              <GapsSection gaps={r.knowledge_gaps} />
              {r.iteration_metrics?.length > 0 && <ProgressChart metrics={r.iteration_metrics} />}
              <MetadataStrip report={r} onExport={() => setShowExport(true)} />
            </>
          )}

          {/* Network Map */}
          {activeNav === 'network' && !deepDiveHypothesis && (
            <AgentNetworkMap agentStates={agentStates} report={r} isRunning={isRunning} />
          )}

          {/* Knowledge Base */}
          {activeNav === 'knowledge' && !deepDiveHypothesis && (
            <KnowledgeBase sessions={sessions} reports={cachedReports} onOpenSession={loadReport} />
          )}

          {/* Interactive Decision Center */}
          {activeNav === 'interactive' && !deepDiveHypothesis && (
            <InteractiveCenter agentStates={agentStates} progressMsg={progressMsg} currentIteration={currentIteration} isRunning={isRunning} objective={objective} />
          )}

          {r && activeNav === 'claims' && !deepDiveHypothesis && <ClaimsSection claims={r.key_claims} expanded />}
          {r && activeNav === 'gaps' && !deepDiveHypothesis && <GapsSection gaps={r.knowledge_gaps} expanded />}
          {r && activeNav === 'progress' && !deepDiveHypothesis && r.iteration_metrics?.length > 0 && <ProgressChart metrics={r.iteration_metrics} />}
          {r && activeNav === 'reports' && !deepDiveHypothesis && (
            <div className="flex flex-col items-center justify-center py-16 space-y-4">
              <Icon name="description" className="text-5xl text-primary/50" />
              <h3 className="text-xl font-bold text-white">Export Research Report</h3>
              <p className="text-slate-400 text-sm max-w-md text-center">Download your completed research as JSON, Markdown, or printable HTML</p>
              <button onClick={() => setShowExport(true)} className="mt-4 px-6 py-3 bg-primary hover:bg-primary/90 text-white font-bold rounded-xl shadow-lg shadow-primary/20 flex items-center gap-2 transition-all">
                <Icon name="file_download" className="text-sm" /> Export Report
              </button>
            </div>
          )}
        </div>

        {/* Export Modal */}
        {showExport && <ReportExport report={r} onClose={() => setShowExport(false)} />}
      </main>
    </div>
  )
}

/* ═══════════════════════ Components ═══════════════════════ */

function ScoreCards({ report: r }) {
  const cards = [
    { label: 'Hypothesis Confidence', value: r.final_hypothesis_confidence, icon: 'lightbulb', color: 'amber', delta: '+2.1%' },
    { label: 'Epistemic Risk', value: r.final_epistemic_risk, icon: 'security', color: 'emerald', delta: '-0.5%' },
    { label: 'Novelty Score', value: r.final_novelty_score, icon: 'auto_awesome', color: 'primary', delta: '+5.2%' },
  ]

  const circumference = 2 * Math.PI * 28
  const colorMap = { amber: '#f59e0b', emerald: '#10b981', primary: '#833cf6' }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {cards.map(c => {
        const offset = circumference - Math.min(c.value, 1) * circumference
        const clr = colorMap[c.color]
        return (
          <div key={c.label} className="glass-card rounded-2xl p-6 flex items-center justify-between overflow-hidden relative group hover:bg-white/5 transition-all duration-300 cursor-pointer">
            <div className={`absolute top-0 right-0 w-24 h-24 bg-${c.color}-500/10 rounded-full blur-3xl -mr-8 -mt-8`}></div>
            <div>
              <p className="text-sm font-medium text-slate-400 mb-1">{c.label}</p>
              <h3 className="text-3xl font-bold text-white tracking-tight">{(c.value * 100).toFixed(1)}%</h3>
              <p className="text-xs mt-2 font-semibold flex items-center gap-1" style={{ color: clr }}>
                <Icon name={c.label.includes('Risk') ? 'verified' : 'trending_up'} className="text-sm" /> {c.delta}
              </p>
            </div>
            <div className="relative size-16">
              <svg className="w-full h-full transform -rotate-90">
                <circle className="text-slate-800" cx="32" cy="32" fill="transparent" r="28" stroke="currentColor" strokeWidth="4" />
                <circle cx="32" cy="32" fill="transparent" r="28" stroke={clr} strokeWidth="4"
                  strokeDasharray={circumference} strokeDashoffset={offset}
                  style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)' }} />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <Icon name={c.icon} className="text-xl" style={{ color: clr }} />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ConclusionCard({ conclusion, report }) {
  return (
    <div className="glass-card rounded-2xl overflow-hidden border-t-4 border-t-emerald-500">
      <div className="p-4 bg-white/5 border-b border-white/5 flex items-center justify-between">
        <h4 className="font-bold text-lg flex items-center gap-2 text-white">
          <span className="text-xl">🎯</span> Key Findings & Conclusion
        </h4>
        <span className="px-2 py-1 bg-emerald-500/10 text-emerald-400 text-[10px] font-bold rounded uppercase border border-emerald-500/20">
          Verified
        </span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 divide-y lg:divide-y-0 lg:divide-x divide-white/10">
        <div className="lg:col-span-2 p-6">
          <h5 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Primary Conclusion</h5>
          <p className="text-slate-300 leading-relaxed text-sm whitespace-pre-line">{conclusion}</p>
        </div>
        <div className="p-6 bg-cyan-500/5">
          <h5 className="text-xs font-bold text-cyan-400/80 uppercase tracking-widest mb-4 flex items-center gap-2">
            <Icon name="summarize" className="text-sm" /> Executive Stats
          </h5>
          <div className="space-y-3">
            {[
              ['Claims Extracted', report.key_claims?.length || 0],
              ['Hypotheses', report.hypotheses?.length || 0],
              ['Knowledge Gaps', report.knowledge_gaps?.length || 0],
              ['Iterations', report.total_iterations],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between items-center text-sm">
                <span className="text-slate-400">{k}</span>
                <span className="font-mono text-cyan-400 font-bold">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function HypothesesSection({ hypotheses, onDeepDive }) {
  if (!hypotheses?.length) return null
  return (
    <section>
      <h5 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
        <Icon name="layers" className="text-sm" /> Active Hypotheses
        <span className="ml-2 bg-primary/15 text-primary text-[10px] font-bold px-2 py-0.5 rounded-full">{hypotheses.length}</span>
      </h5>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {hypotheses.map((h, i) => {
          const conf = h.confidence ?? 0
          const barColor = conf > 0.7 ? 'from-primary to-emerald-400' : conf > 0.4 ? 'from-primary to-amber-500' : 'bg-slate-600'
          const confColor = conf > 0.7 ? 'text-emerald-400' : conf > 0.4 ? 'text-amber-400' : 'text-slate-400'
          return (
            <div key={h.id || i} className="glass-card p-5 rounded-2xl flex flex-col group relative hover:border-primary/40 transition-all duration-300">
              <div className="flex justify-between items-start mb-3">
                <span className="text-[10px] font-mono text-primary font-bold bg-primary/10 px-2 py-0.5 rounded border border-primary/20">{h.id}</span>
                <div className="flex gap-1">
                  {(h.supporting_claim_ids || []).slice(0, 3).map((_, j) => (
                    <span key={j} className="size-1.5 rounded-full bg-emerald-400 shadow shadow-emerald-400/50" />
                  ))}
                  {(h.opposing_claim_ids || []).slice(0, 2).map((_, j) => (
                    <span key={j} className="size-1.5 rounded-full bg-rose-400 shadow shadow-rose-400/50" />
                  ))}
                </div>
              </div>
              <p className="text-sm text-slate-200 font-medium mb-4 line-clamp-2">{h.statement}</p>
              <div className="space-y-3 mb-4">
                <div>
                  <div className="flex justify-between text-[10px] text-slate-500 mb-1 font-bold">
                    <span>CONFIDENCE</span>
                    <span className={confColor}>{(conf * 100).toFixed(0)}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className={`h-full bg-gradient-to-r ${barColor} rounded-full transition-all duration-1000`} style={{ width: `${conf * 100}%` }} />
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-between mt-auto">
                <div className="flex gap-3 text-[10px] text-slate-500">
                  <span className="text-emerald-400">▲ {h.supporting_claim_ids?.length || 0}</span>
                  <span className="text-rose-400">▼ {h.opposing_claim_ids?.length || 0}</span>
                </div>
                {onDeepDive && (
                  <button onClick={() => onDeepDive(h)} className="text-[10px] font-bold text-primary hover:text-white bg-primary/10 hover:bg-primary/30 px-2 py-1 rounded border border-primary/20 transition-all flex items-center gap-1">
                    <Icon name="open_in_new" className="text-[10px]" /> Deep Dive
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function ClaimsSection({ claims, expanded = false }) {
  const [showAll, setShowAll] = useState(expanded)
  if (!claims?.length) return null
  const shown = showAll ? claims : claims.slice(0, 8)

  return (
    <section>
      <div className="flex justify-between items-center mb-4">
        <h5 className="text-sm font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
          <Icon name="link" className="text-sm" /> Key Claims
          <span className="ml-2 bg-primary/15 text-primary text-[10px] font-bold px-2 py-0.5 rounded-full">{claims.length}</span>
        </h5>
        {claims.length > 8 && (
          <button className="text-xs text-primary font-bold hover:underline" onClick={() => setShowAll(!showAll)}>
            {showAll ? 'Show Less' : 'View All Claims'}
          </button>
        )}
      </div>
      <div className="glass-card rounded-2xl overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="bg-white/5 text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b border-white/5">
              <th className="px-6 py-4">Subject</th>
              <th className="px-6 py-4">Relation</th>
              <th className="px-6 py-4">Object</th>
              <th className="px-6 py-4">Confidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-slate-300">
            {shown.map((c, i) => {
              const conf = c.confidence_estimate ?? 0
              const clr = conf >= 0.8 ? 'emerald' : conf >= 0.5 ? 'amber' : 'rose'
              return (
                <tr key={c.id || i} className="hover:bg-white/5 transition-colors">
                  <td className="px-6 py-4 font-medium text-white">{c.subject}</td>
                  <td className="px-6 py-4 text-cyan-400 italic">{c.relation}</td>
                  <td className="px-6 py-4">{c.object}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <span className="block w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                        <span className={`block h-full bg-${clr}-400 rounded-full`} style={{ width: `${conf * 100}%` }} />
                      </span>
                      <span className={`text-[10px] font-bold text-${clr}-400`}>{(conf * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function GapsSection({ gaps, expanded = false }) {
  if (!gaps?.length) return null
  return (
    <section>
      <h5 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
        <Icon name="error" className="text-sm" /> Knowledge Gaps
        <span className="ml-2 bg-primary/15 text-primary text-[10px] font-bold px-2 py-0.5 rounded-full">{gaps.length}</span>
      </h5>
      <div className="space-y-3">
        {gaps.map((g, i) => {
          const sev = g.severity ?? 0
          const sevConfig = sev >= 0.8
            ? { label: 'HIGH', border: 'border-l-rose-500', badge: 'bg-rose-600/20 text-rose-400 border-rose-500/30', hover: 'hover:bg-rose-500/5' }
            : sev >= 0.5
            ? { label: 'MEDIUM', border: 'border-l-amber-500', badge: 'bg-amber-600/20 text-amber-400 border-amber-500/30', hover: 'hover:bg-amber-500/5' }
            : { label: 'LOW', border: 'border-l-blue-500', badge: 'bg-blue-600/20 text-blue-400 border-blue-500/30', hover: 'hover:bg-blue-500/5' }
          return (
            <div key={g.id || i} className={`glass-card p-4 rounded-xl border-l-4 ${sevConfig.border} flex justify-between items-center ${sevConfig.hover} transition-colors cursor-pointer`}>
              <div className="flex-1 mr-4">
                <p className="text-xs font-bold text-white mb-1">{g.description}</p>
                {g.suggested_queries?.length > 0 && (
                  <div className="flex gap-2 flex-wrap mt-2">
                    {g.suggested_queries.map((q, j) => (
                      <span key={j} className="text-[10px] px-2 py-0.5 bg-primary/10 text-primary rounded-full border border-primary/15">{q}</span>
                    ))}
                  </div>
                )}
              </div>
              <span className={`${sevConfig.badge} text-[10px] font-bold px-3 py-1 rounded border shrink-0`}>{sevConfig.label}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function ProgressChart({ metrics }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !metrics?.length) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr; canvas.height = rect.height * dpr; ctx.scale(dpr, dpr)
    const w = rect.width, h = rect.height
    const pad = { top: 20, right: 32, bottom: 36, left: 48 }
    const cW = w - pad.left - pad.right, cH = h - pad.top - pad.bottom
    ctx.clearRect(0, 0, w, h)

    ctx.strokeStyle = 'rgba(255,255,255,0.04)'; ctx.lineWidth = 1
    for (let i = 0; i <= 4; i++) { const y = pad.top + (cH / 4) * i; ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke() }

    ctx.font = '11px monospace'; ctx.fillStyle = '#64748b'; ctx.textAlign = 'right'
    for (let i = 0; i <= 4; i++) { ctx.fillText(((4 - i) * 0.25).toFixed(2), pad.left - 8, pad.top + (cH / 4) * i + 4) }
    ctx.textAlign = 'center'
    metrics.forEach((m, i) => { ctx.fillText(`${m.iteration}`, pad.left + (cW / Math.max(metrics.length - 1, 1)) * i, h - 8) })

    const series = [
      { key: 'hypothesis_confidence', color: '#833cf6' },
      { key: 'epistemic_risk', color: '#f43f5e' },
      { key: 'novelty_score', color: '#06b6d4' },
    ]
    series.forEach(({ key, color }) => {
      ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 2.5; ctx.lineJoin = 'round'; ctx.lineCap = 'round'
      metrics.forEach((m, i) => {
        const x = pad.left + (cW / Math.max(metrics.length - 1, 1)) * i
        const y = pad.top + cH - (m[key] ?? 0) * cH
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      })
      ctx.stroke()
      metrics.forEach((m, i) => {
        const x = pad.left + (cW / Math.max(metrics.length - 1, 1)) * i
        const y = pad.top + cH - (m[key] ?? 0) * cH
        ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill()
        ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2); ctx.fillStyle = '#0a0e1a'; ctx.fill()
      })
    })
  }, [metrics])

  return (
    <section>
      <div className="flex justify-between items-center mb-4">
        <h5 className="text-sm font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
          <Icon name="monitoring" className="text-sm" /> Research Progress
        </h5>
      </div>
      <div className="glass-card rounded-2xl p-6">
        <canvas ref={canvasRef} className="w-full h-[200px]" />
        <div className="flex justify-center gap-6 mt-4">
          {[['Confidence', '#833cf6'], ['Risk', '#f43f5e'], ['Novelty', '#06b6d4']].map(([l, c]) => (
            <div key={l} className="flex items-center gap-2 text-xs text-slate-400">
              <span className="size-2 rounded-full" style={{ background: c }} /> {l}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function MetadataStrip({ report: r, onExport }) {
  return (
    <div className="flex items-center gap-6 flex-wrap text-[10px] font-mono text-slate-500 uppercase tracking-widest pt-4 border-t border-white/5">
      <span>Session: <span className="text-slate-300">{r.session_id}</span></span>
      <span>Mode: <span className="text-slate-300">{r.mode}</span></span>
      <span>Time: <span className="text-slate-300">{(r.total_execution_time_seconds / 60).toFixed(1)}m</span></span>
      <span>Termination: <span className="text-slate-300">{r.termination_reason}</span></span>
      {onExport && (
        <button onClick={onExport} className="ml-auto flex items-center gap-1 text-primary hover:text-white bg-primary/10 hover:bg-primary/20 px-3 py-1.5 rounded-lg border border-primary/20 transition-all text-[10px] font-bold uppercase tracking-widest">
          <Icon name="file_download" className="text-sm" /> Export
        </button>
      )}
    </div>
  )
}
