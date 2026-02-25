import { useState } from 'react'

const Icon = ({ name, className = '' }) => <span className={`material-symbols-outlined ${className}`}>{name}</span>

export default function HypothesisDeepDive({ hypothesis, report, onBack }) {
  const [evidenceFilter, setEvidenceFilter] = useState('all')
  if (!hypothesis) return null

  const conf = hypothesis.confidence ?? 0
  const supportCount = hypothesis.supporting_claim_ids?.length || 0
  const opposingCount = hypothesis.opposing_claim_ids?.length || 0

  // Get supporting and opposing claims from report
  const allClaims = report?.key_claims || []
  const supportingClaims = allClaims.filter(c => hypothesis.supporting_claim_ids?.includes(c.id))
  const opposingClaims = allClaims.filter(c => hypothesis.opposing_claim_ids?.includes(c.id))
  const allEvidence = [
    ...supportingClaims.map(c => ({ ...c, stance: 'supporting' })),
    ...opposingClaims.map(c => ({ ...c, stance: 'conflicting' })),
  ]
  const filtered = evidenceFilter === 'all' ? allEvidence
    : evidenceFilter === 'supporting' ? allEvidence.filter(e => e.stance === 'supporting')
    : allEvidence.filter(e => e.stance === 'conflicting')

  const circumference = 2 * Math.PI * 64
  const offset = circumference - Math.min(conf, 1) * circumference

  return (
    <div className="min-h-full">
      {/* Breadcrumb & nav */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <a className="hover:text-primary cursor-pointer" onClick={onBack}>Dashboard</a>
          <Icon name="chevron_right" className="text-xs" />
          <span className="text-slate-300">Deep Dive: {hypothesis.id}</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onBack} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 hover:text-primary text-slate-400 text-xs font-semibold transition-colors">
            <Icon name="arrow_back" className="text-sm" /> Back
          </button>
        </div>
      </div>

      {/* Hypothesis title */}
      <div className="max-w-3xl mb-10">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/30 text-primary text-xs font-bold tracking-widest uppercase">
            <Icon name="database" className="text-xs" /> Hypothesis {hypothesis.id}
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400 px-3 py-1 bg-white/5 rounded-full border border-white/5">
            <Icon name="smart_toy" className="text-[14px]" /> Status: <span className="text-slate-200 font-semibold">{hypothesis.status || 'Active'}</span>
          </div>
        </div>
        <h1 className="text-3xl lg:text-4xl font-black text-slate-100 leading-snug tracking-tight">{hypothesis.statement}</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column */}
        <div className="lg:col-span-4 flex flex-col gap-8">
          {/* Confidence Radial */}
          <div className="glass-card p-8 rounded-xl flex flex-col items-center text-center">
            <h3 className="text-slate-400 text-sm font-bold uppercase tracking-widest mb-6">Confidence Score</h3>
            <div className="relative size-40 flex items-center justify-center">
              <svg className="w-full h-full transform -rotate-90">
                <circle cx="80" cy="80" r="64" fill="transparent" stroke="#1e293b" strokeWidth="8" />
                <circle cx="80" cy="80" r="64" fill="transparent" stroke="#833cf6" strokeWidth="8"
                  strokeDasharray={circumference} strokeDashoffset={offset}
                  style={{ transition: 'stroke-dashoffset 1.5s cubic-bezier(0.4,0,0.2,1)' }} />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-4xl font-black text-slate-100">{(conf * 100).toFixed(0)}%</span>
                <span className="text-slate-400 text-xs font-medium">Confidence</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4 w-full mt-8 pt-6 border-t border-white/5">
              <div><p className="text-emerald-400 text-2xl font-bold">{String(supportCount).padStart(2, '0')}</p><p className="text-slate-500 text-xs uppercase font-bold">Supporting</p></div>
              <div><p className="text-rose-400 text-2xl font-bold">{String(opposingCount).padStart(2, '0')}</p><p className="text-slate-500 text-xs uppercase font-bold">Conflicting</p></div>
            </div>
          </div>

          {/* Reasoning Trace */}
          <div className="glass-card p-6 rounded-xl">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-slate-100 font-bold flex items-center gap-2"><Icon name="account_tree" className="text-primary" /> Reasoning Trace</h3>
            </div>
            <div className="space-y-6 relative before:content-[''] before:absolute before:left-3 before:top-2 before:bottom-2 before:w-px before:bg-white/10">
              {[
                { label: 'Data Ingestion', status: 'VALIDATED', color: 'emerald', desc: `Aggregated ${supportCount + opposingCount} evidence items from research sources.` },
                { label: 'Claim Analysis', status: supportCount > opposingCount ? 'CONFIRMED' : 'MIXED', color: supportCount > opposingCount ? 'emerald' : 'amber', desc: `${supportCount} supporting vs ${opposingCount} opposing claims identified.` },
                { label: 'Synthesis', status: conf > 0.7 ? 'HIGH CONFIDENCE' : 'PENDING', color: conf > 0.7 ? 'emerald' : 'primary', desc: `Overall confidence: ${(conf * 100).toFixed(1)}%. ${conf > 0.7 ? 'Hypothesis strongly supported.' : 'Needs further evidence.'}` },
              ].map((step, i) => (
                <div key={i} className="relative pl-8">
                  <div className={`absolute left-1.5 top-1.5 size-3 rounded-full bg-${step.color}-500 border-4 border-bg-dark`}></div>
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="text-sm font-bold text-slate-200">{step.label}</h4>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold bg-${step.color}-500/10 text-${step.color}-400 border border-${step.color}-500/20`}>{step.status}</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">{step.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column - Evidence */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          <div className="flex items-center justify-between gap-4">
            <h3 className="text-xl font-bold text-slate-100">Evidence & Citations</h3>
            <div className="flex p-1 rounded-lg bg-white/5 border border-white/10">
              {[
                { key: 'all', label: `All (${allEvidence.length})` },
                { key: 'supporting', label: `Supporting (${supportingClaims.length})` },
                { key: 'conflicting', label: `Conflicting (${opposingClaims.length})` },
              ].map(f => (
                <button key={f.key}
                  className={`px-4 py-1.5 text-xs rounded-md font-bold transition-colors whitespace-nowrap ${evidenceFilter === f.key ? 'bg-primary text-white shadow-sm' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}
                  onClick={() => setEvidenceFilter(f.key)}>{f.label}</button>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            {filtered.length === 0 && <p className="text-slate-500 text-sm py-8 text-center">No evidence items found for this filter.</p>}
            {filtered.map((ev, i) => (
              <div key={ev.id || i} className={`glass-card p-5 rounded-xl border-l-4 ${ev.stance === 'supporting' ? 'border-l-emerald-500' : 'border-l-rose-500'} hover:bg-white/[0.07] transition-all group`}>
                <div className="flex justify-between items-start mb-3">
                  <div className="flex flex-col">
                    <span className={`${ev.stance === 'supporting' ? 'text-emerald-400' : 'text-rose-400'} text-[10px] font-bold uppercase tracking-widest mb-1`}>
                      {ev.stance === 'supporting' ? 'Supporting Evidence' : 'Conflicting Evidence'}
                    </span>
                    <h4 className="text-slate-100 font-bold">{ev.subject} {ev.relation} {ev.object}</h4>
                  </div>
                  <span className={`${ev.stance === 'supporting' ? 'bg-primary/20 text-primary' : 'bg-slate-700/50 text-slate-400'} px-2 py-1 rounded text-[10px] font-black`}>
                    {((ev.confidence_estimate || 0) * 100).toFixed(0)}% CONF.
                  </span>
                </div>
                {ev.source_text && (
                  <p className="text-slate-400 text-sm leading-7 mb-4 italic border-l-2 border-white/10 pl-4">{ev.source_text}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
