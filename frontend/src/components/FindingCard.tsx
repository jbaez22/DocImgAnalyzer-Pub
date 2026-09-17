import type { Finding } from '../types/api'

const SEVERITY_STYLES = {
  ERROR: {
    badge: 'bg-red-100 text-red-700 border border-red-200',
    border: 'border-l-red-500',
    icon: '✕',
  },
  WARNING: {
    badge: 'bg-amber-100 text-amber-700 border border-amber-200',
    border: 'border-l-amber-400',
    icon: '⚠',
  },
  INFO: {
    badge: 'bg-blue-100 text-blue-700 border border-blue-200',
    border: 'border-l-blue-400',
    icon: 'ℹ',
  },
}

interface Props {
  finding: Finding
}

export default function FindingCard({ finding }: Props) {
  const style = SEVERITY_STYLES[finding.severity]

  return (
    <div className={`rounded-lg border border-slate-200 bg-white p-4 border-l-4 ${style.border}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${style.badge}`}>
              {style.icon} {finding.severity}
            </span>
            <span className="text-xs font-mono text-slate-400">{finding.rule_id}</span>
            {finding.line !== null && (
              <span className="text-xs text-slate-400">Line {finding.line}</span>
            )}
          </div>
          <p className="mt-2 font-semibold text-slate-800">{finding.title}</p>
          <p className="mt-1 text-sm text-slate-600 leading-relaxed">{finding.description}</p>
          {finding.fix && (
            <div className="mt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1">Fix</p>
              <pre className="rounded-md bg-slate-900 px-3 py-2 text-xs text-emerald-300 overflow-x-auto whitespace-pre-wrap">{finding.fix}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
