import { useState, useRef } from 'react'

const Icon = ({ name, className = '' }) => <span className={`material-symbols-outlined ${className}`}>{name}</span>

export default function ReportExport({ report, onClose }) {
  const [format, setFormat] = useState('json')
  const [exporting, setExporting] = useState(false)

  if (!report) return null

  const exportReport = () => {
    setExporting(true)
    let content, filename, mimeType

    if (format === 'json') {
      content = JSON.stringify(report, null, 2)
      filename = `aro_report_${report.session_id}.json`
      mimeType = 'application/json'
    } else if (format === 'markdown') {
      content = generateMarkdown(report)
      filename = `aro_report_${report.session_id}.md`
      mimeType = 'text/markdown'
    } else {
      // For PDF, export as HTML that can be printed
      content = generatePrintableHTML(report)
      filename = `aro_report_${report.session_id}.html`
      mimeType = 'text/html'
    }

    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
    setTimeout(() => setExporting(false), 500)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(4,7,14,0.85)', backdropFilter: 'blur(8px)' }}>
      <div className="glass-card rounded-2xl w-full max-w-lg overflow-hidden">
        <div className="p-6 border-b border-white/10 flex items-center justify-between">
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <Icon name="file_download" className="text-primary" /> Export Report
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition-colors">
            <Icon name="close" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div>
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Research Objective</p>
            <p className="text-sm text-slate-200 font-medium">{report.research_objective}</p>
          </div>

          <div>
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Export Format</p>
            <div className="grid grid-cols-3 gap-3">
              {[
                { key: 'json', label: 'JSON', icon: 'data_object', desc: 'Raw structured data' },
                { key: 'markdown', label: 'Markdown', icon: 'description', desc: 'Formatted report' },
                { key: 'html', label: 'HTML / PDF', icon: 'picture_as_pdf', desc: 'Printable document' },
              ].map(f => (
                <button key={f.key}
                  className={`p-4 rounded-xl border text-left transition-all ${format === f.key ? 'border-primary/40 bg-primary/10' : 'border-white/10 hover:border-white/20 hover:bg-white/5'}`}
                  onClick={() => setFormat(f.key)}>
                  <Icon name={f.icon} className={`text-2xl mb-2 ${format === f.key ? 'text-primary' : 'text-slate-500'}`} />
                  <p className="text-sm font-bold text-white">{f.label}</p>
                  <p className="text-[10px] text-slate-500 mt-1">{f.desc}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="glass-card rounded-xl p-4">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Report Summary</p>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="flex justify-between"><span className="text-slate-400">Hypotheses</span><span className="text-white font-mono font-bold">{report.hypotheses?.length || 0}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Claims</span><span className="text-white font-mono font-bold">{report.key_claims?.length || 0}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Iterations</span><span className="text-white font-mono font-bold">{report.total_iterations}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Tokens Used</span><span className="text-white font-mono font-bold">{report.total_tokens_used?.toLocaleString()}</span></div>
            </div>
          </div>
        </div>

        <div className="p-6 border-t border-white/10 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm font-bold text-slate-300 hover:bg-white/10 transition-colors">Cancel</button>
          <button onClick={exportReport} disabled={exporting}
            className="px-6 py-2 rounded-lg bg-primary hover:bg-primary/90 text-white text-sm font-bold shadow-lg shadow-primary/20 transition-all disabled:opacity-50 flex items-center gap-2">
            {exporting ? <><span className="spinner" /> Exporting...</> : <><Icon name="download" className="text-sm" /> Export</>}
          </button>
        </div>
      </div>
    </div>
  )
}

function generateMarkdown(r) {
  let md = `# ARO Research Report\n\n`
  md += `**Objective:** ${r.research_objective}\n\n`
  md += `**Mode:** ${r.mode} | **Iterations:** ${r.total_iterations} | **Tokens:** ${r.total_tokens_used?.toLocaleString()}\n\n`
  if (r.conclusion) md += `## Conclusion\n\n${r.conclusion}\n\n`
  md += `## Executive Summary\n\n${r.executive_summary}\n\n`
  md += `## Key Metrics\n\n| Metric | Value |\n|--------|-------|\n`
  md += `| Hypothesis Confidence | ${(r.final_hypothesis_confidence * 100).toFixed(1)}% |\n`
  md += `| Epistemic Risk | ${(r.final_epistemic_risk * 100).toFixed(1)}% |\n`
  md += `| Novelty Score | ${(r.final_novelty_score * 100).toFixed(1)}% |\n\n`
  if (r.hypotheses?.length) {
    md += `## Hypotheses\n\n`
    r.hypotheses.forEach(h => { md += `### ${h.id}: ${h.statement}\n- Confidence: ${((h.confidence || 0) * 100).toFixed(0)}%\n- Supporting: ${h.supporting_claim_ids?.length || 0} | Opposing: ${h.opposing_claim_ids?.length || 0}\n\n` })
  }
  if (r.key_claims?.length) {
    md += `## Key Claims\n\n| Subject | Relation | Object | Confidence |\n|---------|----------|--------|------------|\n`
    r.key_claims.forEach(c => { md += `| ${c.subject} | ${c.relation} | ${c.object} | ${((c.confidence_estimate || 0) * 100).toFixed(0)}% |\n` })
  }
  return md
}

function generatePrintableHTML(r) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>ARO Report - ${r.research_objective}</title>
<style>body{font-family:Inter,sans-serif;max-width:800px;margin:0 auto;padding:40px;color:#1e293b;}
h1{color:#833cf6;border-bottom:2px solid #833cf6;padding-bottom:8px;}
h2{color:#334155;margin-top:32px;}
table{width:100%;border-collapse:collapse;margin:16px 0;}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid #e2e8f0;}
th{background:#f8fafc;font-size:12px;text-transform:uppercase;letter-spacing:0.05em;}
.metric{display:inline-block;padding:12px 20px;margin:4px;background:#f8fafc;border-radius:8px;text-align:center;}
.metric .value{font-size:24px;font-weight:800;color:#833cf6;}
.metric .label{font-size:10px;text-transform:uppercase;color:#64748b;}
.conclusion{background:#f0fdf4;border-left:4px solid #10b981;padding:16px;margin:16px 0;border-radius:0 8px 8px 0;}
@media print{body{padding:20px;}}</style></head><body>
<h1>ARO Research Report</h1><p><strong>Objective:</strong> ${r.research_objective}</p>
<div class="metric"><div class="value">${(r.final_hypothesis_confidence * 100).toFixed(1)}%</div><div class="label">Confidence</div></div>
<div class="metric"><div class="value">${(r.final_epistemic_risk * 100).toFixed(1)}%</div><div class="label">Risk</div></div>
<div class="metric"><div class="value">${(r.final_novelty_score * 100).toFixed(1)}%</div><div class="label">Novelty</div></div>
${r.conclusion ? `<h2>Conclusion</h2><div class="conclusion">${r.conclusion}</div>` : ''}
<h2>Executive Summary</h2><p>${r.executive_summary}</p>
${r.hypotheses?.length ? `<h2>Hypotheses</h2><table><tr><th>ID</th><th>Statement</th><th>Confidence</th></tr>${r.hypotheses.map(h => `<tr><td>${h.id}</td><td>${h.statement}</td><td>${((h.confidence || 0) * 100).toFixed(0)}%</td></tr>`).join('')}</table>` : ''}
${r.key_claims?.length ? `<h2>Key Claims</h2><table><tr><th>Subject</th><th>Relation</th><th>Object</th><th>Conf.</th></tr>${r.key_claims.map(c => `<tr><td>${c.subject}</td><td>${c.relation}</td><td>${c.object}</td><td>${((c.confidence_estimate || 0) * 100).toFixed(0)}%</td></tr>`).join('')}</table>` : ''}
<p style="color:#94a3b8;font-size:11px;margin-top:40px;">Generated by ARO — Autonomous Research Operator | Session: ${r.session_id} | ${r.total_iterations} iterations, ${r.total_tokens_used?.toLocaleString()} tokens</p>
</body></html>`
}
