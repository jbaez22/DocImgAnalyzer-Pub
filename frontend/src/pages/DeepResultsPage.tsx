import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { cancelScan, getResultV2 } from '../api/client'
import CveFindings from '../components/CveFindings'
import FindingCard from '../components/FindingCard'
import LoadingSpinner from '../components/LoadingSpinner'
import NavBar from '../components/NavBar'
import ScoreGauge from '../components/ScoreGauge'
import type { Finding, ScanResult, Severity } from '../types/api'

const POLL_INTERVAL_MS = 5000
const SEVERITY_ORDER: Severity[] = ['ERROR', 'WARNING', 'INFO']

function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity),
  )
}

function findingCount(findings: Finding[], severity: Severity): number {
  return findings.filter(f => f.severity === severity).length
}

interface CveCardProps {
  count: number | null
  label: string
  colorClass: string
}

function CveCard({ count, label, colorClass }: CveCardProps) {
  return (
    <div className={`flex flex-col items-center justify-center rounded-xl border-2 p-5 ${colorClass}`}>
      <span className="text-4xl font-bold tabular-nums">{count ?? '—'}</span>
      <span className="mt-1 text-xs font-medium uppercase tracking-wide opacity-80">{label}</span>
    </div>
  )
}

function DownloadButton({ url, label, filename }: { url: string | null; label: string; filename: string }) {
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  if (!url) return null

  async function handleDownload() {
    if (!url) return
    setDownloading(true)
    setDownloadError(null)
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(blobUrl)
    } catch {
      setDownloadError('Download failed — link may have expired')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <button
        onClick={handleDownload}
        disabled={downloading}
        className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <span>&#8595;</span> {downloading ? 'Downloading…' : label}
      </button>
      {downloadError && <p className="text-xs text-red-500">{downloadError}</p>}
    </div>
  )
}

function DockerfileResults({ result }: { result: ScanResult }) {
  const findings = result.findings ?? []
  const sorted = sortFindings(findings)
  const errorCount = findingCount(findings, 'ERROR')
  const warningCount = findingCount(findings, 'WARNING')
  const infoCount = findingCount(findings, 'INFO')

  return (
    <>
      {/* Score + finding counts */}
      <section>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          <div className="sm:col-span-1">
            <ScoreGauge score={result.score ?? 0} />
          </div>
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
        </div>
      </section>

      {/* Findings */}
      <section>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
          Findings ({sorted.length})
        </h3>
        {sorted.length === 0 ? (
          <div className="rounded-xl border-2 border-dashed border-emerald-200 bg-emerald-50 p-8 text-center">
            <p className="text-emerald-700 font-semibold">No findings — looks great!</p>
          </div>
        ) : (
          <div className="space-y-3">
            {sorted.map((f, i) => (
              <FindingCard key={`${f.rule_id}-${i}`} finding={f} />
            ))}
          </div>
        )}
      </section>

      {/* Fixed Dockerfile */}
      {result.fixed_dockerfile && (
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
            Fixed Dockerfile
          </h3>
          <div className="rounded-xl border border-slate-200 bg-slate-900 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700">
              <span className="text-xs font-medium text-slate-400">Dockerfile</span>
              <span className="text-xs text-emerald-400">All fixes applied</span>
            </div>
            <pre className="px-4 py-4 text-xs text-slate-200 overflow-x-auto leading-relaxed whitespace-pre">{result.fixed_dockerfile}</pre>
          </div>
        </section>
      )}
    </>
  )
}

function ImageResults({ result }: { result: ScanResult }) {
  const scanId = result.scan_id.slice(0, 8)
  return (
    <>
      {/* CVE Summary */}
      <section>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
          CVE Summary
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <CveCard count={result.cve_critical} label="Critical" colorClass="text-red-600 bg-red-50 border-red-200" />
          <CveCard count={result.cve_high} label="High" colorClass="text-orange-600 bg-orange-50 border-orange-200" />
          <CveCard count={result.cve_medium} label="Medium" colorClass="text-amber-600 bg-amber-50 border-amber-200" />
          <CveCard count={result.cve_low} label="Low" colorClass="text-slate-600 bg-slate-50 border-slate-200" />
        </div>
      </section>

      {/* Downloads */}
      {(result.report_url || result.sbom_url) && (
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
            Downloads
          </h3>
          <div className="flex flex-wrap gap-3">
            <DownloadButton url={result.report_url} label="CVE Report (JSON)" filename={`cve-report-${scanId}.json`} />
            <DownloadButton url={result.sbom_url} label="SBOM (SPDX JSON)" filename={`sbom-${scanId}.spdx.json`} />
          </div>
          <p className="mt-2 text-xs text-slate-400">Download links expire in 5 hours.</p>
        </section>
      )}

      {/* CVE Findings — inline from report JSON */}
      {result.report_url && (
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-3">
            Vulnerability Details
          </h3>
          <CveFindings reportUrl={result.report_url} imageName={result.image_name} />
        </section>
      )}
    </>
  )
}

export default function DeepResultsPage() {
  const { scanId } = useParams<{ scanId: string }>()
  const navigate = useNavigate()

  const [result, setResult] = useState<ScanResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  async function handleCancel() {
    if (!scanId) return
    setCancelling(true)
    stopPolling()
    try {
      await cancelScan(scanId)
      setResult(prev => prev ? { ...prev, status: 'CANCELLED' } : prev)
    } catch {
      setCancelling(false)
      pollRef.current = setInterval(fetchResult, POLL_INTERVAL_MS)
    }
  }

  async function fetchResult() {
    if (!scanId) return
    try {
      const data = await getResultV2(scanId)
      setResult(data)
      if (data.status === 'COMPLETE' || data.status === 'FAILED' || data.status === 'CANCELLED') {
        stopPolling()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load result.')
      stopPolling()
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchResult()
    return stopPolling
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanId])

  useEffect(() => {
    if (!result) return
    if (result.status === 'PENDING' || result.status === 'PROCESSING') {
      pollRef.current = setInterval(fetchResult, POLL_INTERVAL_MS)
    } else {
      stopPolling()
    }
    return stopPolling
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.status])

  if (loading) return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <NavBar />
      <div className="flex-1 flex items-center justify-center">
        <LoadingSpinner message="Loading scan result…" />
      </div>
    </div>
  )

  if (error || !result) {
    return (
      <div className="min-h-screen flex flex-col bg-slate-50">
        <NavBar />
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="text-center max-w-md">
            <p className="text-red-600 font-semibold">{error ?? 'Scan not found.'}</p>
            <button onClick={() => navigate('/dashboard')} className="mt-4 text-sm text-blue-600 hover:underline">
              Back to dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }

  const isPending = result.status === 'PENDING' || result.status === 'PROCESSING'
  const isDockerfile = result.scan_type === 'dockerfile'
  const isKubernetes = result.scan_type === 'kubernetes'
  const isFindingsBased = isDockerfile || isKubernetes

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <NavBar />

      <header className="bg-white border-b border-slate-200">
        <div className="mx-auto max-w-4xl px-4 py-4 flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors"
          >
            <span>&#8592;</span> Dashboard
          </button>
          <div className="h-4 w-px bg-slate-200" />
          <span className="text-sm font-medium text-slate-700 font-mono truncate">
            {isDockerfile
              ? 'Dockerfile Analysis'
              : isKubernetes
                ? 'Kubernetes Manifest Analysis'
                : (result.image_name ?? 'Image Scan')}
          </span>
          <span className={`ml-auto inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
            result.status === 'COMPLETE' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
            result.status === 'FAILED' ? 'bg-red-50 text-red-700 border-red-200' :
            result.status === 'CANCELLED' ? 'bg-slate-100 text-slate-600 border-slate-300' :
            'bg-amber-50 text-amber-700 border-amber-200'
          }`}>
            {result.status}
          </span>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-4xl px-4 py-10 space-y-8">
        {isPending && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="h-4 w-4 rounded-full border-2 border-amber-500 border-t-transparent animate-spin shrink-0" />
              <p className="text-sm text-amber-700 font-medium">
                Scan is {result.status.toLowerCase()}. This page will update automatically every 5 seconds.
              </p>
            </div>
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="shrink-0 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {cancelling ? 'Cancelling…' : 'Cancel Scan'}
            </button>
          </div>
        )}

        {result.status === 'CANCELLED' && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 flex items-center gap-3">
            <p className="text-sm text-slate-600 font-medium">
              Scan was cancelled.{' '}
              <button onClick={() => navigate('/dashboard')} className="text-blue-600 hover:underline">
                Back to dashboard
              </button>
            </p>
          </div>
        )}

        {result.status === 'FAILED' && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6">
            <p className="text-sm text-red-700 font-medium">Scan failed. Please try submitting the image again.</p>
          </div>
        )}

        {result.status === 'COMPLETE' && (
          isFindingsBased
            ? <DockerfileResults result={result} />
            : <ImageResults result={result} />
        )}

        {/* Scan info */}
        <section className="text-xs text-slate-400 space-y-0.5">
          <p>Scan ID: <span className="font-mono">{result.scan_id}</span></p>
          {!isFindingsBased && result.image_name && (
            <p>Image: <span className="font-mono">{result.image_name}</span></p>
          )}
          <p>Submitted: {new Date(result.created_at).toLocaleString()}</p>
        </section>
      </main>

      <footer className="py-6 text-center text-xs text-slate-400">
        Docker & Kubernetes Analyzer &mdash; Phase 2
      </footer>
    </div>
  )
}
