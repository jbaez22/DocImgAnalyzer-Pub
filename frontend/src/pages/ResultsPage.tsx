import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { getResult } from '../api/client'
import FindingCard from '../components/FindingCard'
import LoadingSpinner from '../components/LoadingSpinner'
import NavBar from '../components/NavBar'
import ScoreGauge from '../components/ScoreGauge'
import type { AnalysisReport, Finding, Severity } from '../types/api'

const SEVERITY_ORDER: Severity[] = ['ERROR', 'WARNING', 'INFO']

function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity),
  )
}

function findingCount(findings: Finding[], severity: Severity): number {
  return findings.filter(f => f.severity === severity).length
}

function formatMetadataValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(formatMetadataValue).join(', ')
  }
  if (value !== null && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).map(formatMetadataValue).join('/')
  }
  return String(value)
}

function MetadataTable({ metadata }: { metadata: Record<string, unknown> }) {
  const rows = Object.entries(metadata).filter(([, v]) => v !== null && v !== undefined && v !== '')
  if (!rows.length) return null
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <tbody className="divide-y divide-slate-100">
          {rows.map(([key, value]) => (
            <tr key={key}>
              <td className="px-4 py-2.5 font-medium text-slate-500 w-48 align-top">
                {key.replace(/_/g, ' ')}
              </td>
              <td className="px-4 py-2.5 font-mono text-slate-800 break-all">
                {formatMetadataValue(value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function ResultsPage() {
  const { scanId } = useParams<{ scanId: string }>()
  const location = useLocation()
  const navigate = useNavigate()

  const [report, setReport] = useState<AnalysisReport | null>(
    (location.state as { report?: AnalysisReport } | null)?.report ?? null,
  )
  const [loading, setLoading] = useState(!report)
  const [error, setError] = useState<string | null>(null)

  // If we landed here directly (e.g. from a shared URL), fetch the result
  useEffect(() => {
    if (report || !scanId) return
    getResult(scanId)
      .then(setReport)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load result.'))
      .finally(() => setLoading(false))
  }, [scanId, report])

  if (loading) return <LoadingSpinner message="Loading scan result..." />

  if (error || !report) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center max-w-md">
          <p className="text-red-600 font-semibold">{error ?? 'Scan not found.'}</p>
          <button
            onClick={() => navigate('/')}
            className="mt-4 text-sm text-blue-600 hover:underline"
          >
            Back to home
          </button>
        </div>
      </div>
    )
  }

  const isDockerfile = report.scan_type === 'dockerfile'
  const isKubernetes = report.scan_type === 'kubernetes'
  const isFindingsBased = isDockerfile || isKubernetes
  const sorted = sortFindings(report.findings)
  const errorCount = findingCount(report.findings, 'ERROR')
  const warningCount = findingCount(report.findings, 'WARNING')
  const infoCount = findingCount(report.findings, 'INFO')

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <NavBar />
      <header className="bg-white border-b border-slate-200">
        <div className="mx-auto max-w-4xl px-4 py-4 flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
          >
            <span>&#8592;</span> New analysis
          </button>
          <div className="h-4 w-px bg-slate-200" />
          <span className="text-sm font-medium text-slate-700">
            {isDockerfile ? 'Dockerfile Analysis' : isKubernetes ? 'Kubernetes Manifest Analysis' : 'Image Metadata'} &mdash; Result
          </span>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-4xl px-4 py-10 space-y-8">
        {/* Summary row */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          {/* Score (Dockerfile/Kubernetes only) */}
          {isFindingsBased && report.score !== null ? (
            <div className="sm:col-span-1">
              <ScoreGauge score={report.score} />
            </div>
          ) : (
            <div className="sm:col-span-1 flex items-center justify-center rounded-2xl border-2 border-slate-200 bg-white p-8">
              <div className="text-center">
                <p className="text-3xl font-bold text-blue-600">
                  {report.metadata.layer_count as number ?? '—'}
                </p>
                <p className="mt-1 text-sm text-slate-500">Layers</p>
              </div>
            </div>
          )}

          {/* Finding counts (Dockerfile/Kubernetes only) */}
          {isFindingsBased ? (
            <div className="sm:col-span-2 grid grid-cols-3 gap-4">
              {[
                { label: 'Errors', count: errorCount, color: 'text-red-600 bg-red-50 border-red-200' },
                { label: 'Warnings', count: warningCount, color: 'text-amber-600 bg-amber-50 border-amber-200' },
                { label: 'Info', count: infoCount, color: 'text-blue-600 bg-blue-50 border-blue-200' },
              ].map(({ label, count, color }) => (
                <div key={label} className={`flex flex-col items-center justify-center rounded-xl border-2 p-5 ${color}`}>
                  <span className="text-4xl font-bold tabular-nums">{count}</span>
                  <span className="mt-1 text-xs font-medium uppercase tracking-wide opacity-80">{label}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="sm:col-span-2 flex items-center">
              <div className="w-full rounded-xl border border-slate-200 bg-white p-5 space-y-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Image</p>
                <p className="font-mono text-slate-800 break-all">{String(report.metadata.namespace)}/{String(report.metadata.name)}:{String(report.metadata.tag)}</p>
                {!!report.metadata.digest && (
                  <>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 pt-2">Digest</p>
                    <p className="font-mono text-xs text-slate-600 break-all">{String(report.metadata.digest)}</p>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Findings (Dockerfile/Kubernetes only) */}
        {isFindingsBased && (
          <section>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
              Findings ({sorted.length})
            </h3>
            {sorted.length === 0 ? (
              <div className="rounded-xl border-2 border-dashed border-emerald-200 bg-emerald-50 p-8 text-center">
                <p className="text-emerald-700 font-semibold">
                  {isDockerfile ? 'No findings — great Dockerfile!' : 'No findings — great manifest!'}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {sorted.map((f, i) => (
                  <FindingCard key={`${f.rule_id}-${i}`} finding={f} />
                ))}
              </div>
            )}
          </section>
        )}

        {/* Fixed Dockerfile */}
        {isDockerfile && report.fixed_dockerfile && (
          <section>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
              Fixed Dockerfile
            </h3>
            <div className="rounded-xl border border-slate-200 bg-slate-900 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700">
                <span className="text-xs font-medium text-slate-400">Dockerfile</span>
                <span className="text-xs text-emerald-400">All fixes applied</span>
              </div>
              <pre className="px-4 py-4 text-xs text-slate-200 overflow-x-auto leading-relaxed whitespace-pre">{report.fixed_dockerfile}</pre>
            </div>
          </section>
        )}

        {/* Metadata */}
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
            Metadata
          </h3>
          <MetadataTable metadata={report.metadata} />
        </section>

        {/* Scan info */}
        <section className="text-xs text-slate-400 space-y-0.5">
          <p>Scan ID: <span className="font-mono">{report.scan_id}</span></p>
          <p>Created: {new Date(report.created_at).toLocaleString()}</p>
          {report.completed_at && (
            <p>Completed: {new Date(report.completed_at).toLocaleString()}</p>
          )}
        </section>
      </main>

      <footer className="py-6 text-center text-xs text-slate-400">
        Docker & Kubernetes Analyzer &mdash; Phase 1 MVP
      </footer>
    </div>
  )
}
