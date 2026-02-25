import { useState, useMemo } from 'react'

const Icon = ({ name, className = '' }) => <span className={`material-symbols-outlined ${className}`}>{name}</span>

export default function KnowledgeBase({ sessions, reports, onOpenSession }) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedItem, setSelectedItem] = useState(null)

  // Aggregate all hypotheses and claims across all loaded reports
  const allItems = useMemo(() => {
    const items = []
    if (!reports) return items
    Object.entries(reports).forEach(([sessionId, r]) => {
      if (!r) return
      ;(r.hypotheses || []).forEach(h => items.push({ type: 'hypothesis', sessionId, objective: r.research_objective, ...h }))
      ;(r.key_claims || []).forEach(c => items.push({ type: 'claim', sessionId, objective: r.research_objective, ...c }))
    })
    return items
  }, [reports])

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return allItems.slice(0, 20)
    const q = searchQuery.toLowerCase()
    return allItems.filter(item =>
      (item.statement || '').toLowerCase().includes(q) ||
      (item.subject || '').toLowerCase().includes(q) ||
      (item.object || '').toLowerCase().includes(q) ||
      (item.objective || '').toLowerCase().includes(q)
    ).slice(0, 20)
  }, [allItems, searchQuery])

  const totalHypotheses = allItems.filter(i => i.type === 'hypothesis').length
  const totalClaims = allItems.filter(i => i.type === 'claim').length
  const totalSessions = sessions?.length || 0

  const active = selectedItem || filtered[0]

  return (
    <div className="flex flex-col h-full -m-6">
      {/* Search & Filters Header */}
      <header className="flex flex-col gap-4 px-6 pt-6 pb-4 border-b border-white/10 bg-sidebar-dark/50 z-10">
        <div className="flex flex-col w-full max-w-5xl mx-auto gap-4">
          <div className="relative w-full">
            <div className="absolute inset-y-0 left-0 flex items-center pl-4 pointer-events-none text-slate-400">
              <Icon name="search" />
            </div>
            <input className="w-full h-12 pl-12 pr-4 rounded-xl bg-card-dark border border-white/10 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all shadow-sm"
              placeholder="Search hypotheses, claims, and sources across all sessions..."
              value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
            <div className="absolute inset-y-0 right-0 flex items-center pr-3">
              <span className="text-xs text-slate-500 border border-slate-600 rounded px-1.5 py-0.5">⌘K</span>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap gap-2">
              {['Confidence Score', 'Type', 'Session'].map(f => (
                <button key={f} className="flex items-center gap-2 h-8 px-3 rounded-lg bg-card-dark border border-white/10 hover:border-slate-500 text-slate-300 text-sm font-medium transition-colors">
                  <span>{f}</span><Icon name="expand_more" className="text-base" />
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="w-full px-6 py-4 border-b border-white/10">
        <div className="grid grid-cols-3 gap-4 max-w-5xl mx-auto">
          {[
            { label: 'Total Hypotheses', value: totalHypotheses, icon: 'lightbulb' },
            { label: 'Verified Claims', value: totalClaims, icon: 'verified' },
            { label: 'Research Sessions', value: totalSessions, icon: 'science' },
          ].map(s => (
            <div key={s.label} className="flex items-center justify-between p-4 rounded-xl border border-white/10 bg-card-dark/50 hover:border-primary/50 transition-colors group">
              <div>
                <p className="text-slate-400 text-xs font-medium uppercase tracking-wider">{s.label}</p>
                <p className="text-2xl font-bold text-white mt-1 group-hover:text-primary transition-colors">{s.value.toLocaleString()}</p>
              </div>
              <Icon name={s.icon} className="text-2xl text-slate-600 group-hover:text-primary/50 transition-colors" />
            </div>
          ))}
        </div>
      </div>

      {/* Split View */}
      <div className="flex-1 overflow-hidden flex max-w-5xl mx-auto w-full">
        {/* Left: Results List */}
        <div className="w-[45%] h-full overflow-y-auto border-r border-white/10 p-6 custom-scrollbar">
          <h2 className="text-sm font-semibold text-slate-400 mb-4 sticky top-0 bg-bg-dark z-10 py-2">
            {searchQuery ? `Results for "${searchQuery}"` : 'Most Relevant Results'} ({filtered.length})
          </h2>
          <div className="flex flex-col gap-4">
            {filtered.length === 0 && <p className="text-sm text-slate-500 py-8 text-center">No results found.</p>}
            {filtered.map((item, i) => {
              const isActive = active === item
              const isHyp = item.type === 'hypothesis'
              const conf = isHyp ? (item.confidence || 0) : (item.confidence_estimate || 0)
              const confLabel = conf >= 0.8 ? 'High Confidence' : conf >= 0.5 ? 'Med Confidence' : 'Low Confidence'
              const confColor = conf >= 0.8 ? 'emerald' : conf >= 0.5 ? 'amber' : 'slate'
              return (
                <div key={item.id || i}
                  className={`p-4 rounded-xl cursor-pointer group transition-all relative ${isActive ? 'bg-card-dark border border-primary shadow-[0_0_15px_-3px_rgba(131,60,246,0.15)]' : 'bg-card-dark/40 border border-white/5 hover:bg-card-dark hover:border-white/20'}`}
                  onClick={() => setSelectedItem(item)}>
                  {isActive && <div className="absolute -left-[1px] top-4 bottom-4 w-1 bg-primary rounded-r-full"></div>}
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex items-center gap-2">
                      <span className={`${isHyp ? 'bg-primary/20 text-primary' : 'bg-purple-500/20 text-purple-400'} p-1.5 rounded-lg`}>
                        <Icon name={isHyp ? 'lightbulb' : 'link'} className="text-lg" />
                      </span>
                      <div>
                        <h3 className="text-slate-200 font-semibold text-sm">{isHyp ? `Hypothesis ${item.id}` : `${item.subject}`}</h3>
                        <p className="text-[11px] text-slate-500">Session: <span className="text-slate-400">{(item.objective || '').slice(0, 30)}</span></p>
                      </div>
                    </div>
                    <span className={`bg-${confColor}-500/10 text-${confColor}-400 border border-${confColor}-500/20 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide`}>{confLabel}</span>
                  </div>
                  <p className="text-slate-400 text-sm leading-relaxed line-clamp-2">
                    {isHyp ? item.statement : `${item.subject} ${item.relation} ${item.object}`}
                  </p>
                </div>
              )
            })}
          </div>
        </div>

        {/* Right: Preview */}
        <div className="w-[55%] h-full p-8 overflow-y-auto custom-scrollbar">
          {!active ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <Icon name="search" className="text-5xl mb-4 text-slate-700" />
              <p className="text-sm">Select an item to preview</p>
            </div>
          ) : (
            <div className="glass-card rounded-xl border border-white/10 overflow-hidden flex flex-col">
              <div className="p-6 border-b border-white/10 bg-black/20 flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="bg-primary/20 text-primary p-1 rounded">
                      <Icon name={active.type === 'hypothesis' ? 'lightbulb' : 'link'} className="text-lg" />
                    </span>
                    <span className="text-primary text-xs font-bold tracking-wider uppercase">Deep Dive Preview</span>
                  </div>
                  <h2 className="text-xl font-bold text-white mb-1">
                    {active.type === 'hypothesis' ? active.statement?.slice(0, 60) : `${active.subject} → ${active.object}`}
                  </h2>
                  <p className="text-sm text-slate-400">ID: <span className="font-mono text-slate-300">{active.id}</span></p>
                </div>
                {active.sessionId && (
                  <button onClick={() => onOpenSession?.(active.sessionId)}
                    className="bg-primary hover:bg-primary/90 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2">
                    Open Session <Icon name="arrow_forward" className="text-base" />
                  </button>
                )}
              </div>
              <div className="p-6 space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wide mb-3 flex items-center gap-2">
                    <Icon name="short_text" className="text-base text-primary" /> Details
                  </h3>
                  <p className="text-slate-300 leading-7 text-sm">
                    {active.type === 'hypothesis' ? active.statement : `${active.subject} ${active.relation} ${active.object}`}
                  </p>
                </div>
                {active.type === 'hypothesis' && (
                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-4 rounded-lg bg-black/20 border border-white/5">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Confidence</p>
                      <p className="text-2xl font-bold text-white">{((active.confidence || 0) * 100).toFixed(0)}%</p>
                    </div>
                    <div className="p-4 rounded-lg bg-black/20 border border-white/5">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Evidence</p>
                      <p className="text-2xl font-bold text-white">
                        <span className="text-emerald-400">{active.supporting_claim_ids?.length || 0}</span>
                        <span className="text-slate-600 mx-1">/</span>
                        <span className="text-rose-400">{active.opposing_claim_ids?.length || 0}</span>
                      </p>
                    </div>
                  </div>
                )}
                <div className="pt-4 border-t border-white/5">
                  <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wide mb-3">Source Session</h3>
                  <div className="bg-black/20 p-4 rounded-lg border-l-2 border-primary">
                    <p className="text-xs text-slate-400 mb-1">Research Objective</p>
                    <p className="text-sm text-slate-300">{active.objective}</p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
