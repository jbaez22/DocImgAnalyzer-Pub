import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { deleteScan, getBillingStatus, listScans } from '../api/client'
import { useAuth } from '../auth/useAuth'
import LoadingSpinner from '../components/LoadingSpinner'
import NavBar from '../components/NavBar'
import type { BillingStatus, ScanResult, ScanStatus } from '../types/api'

const TIER_COLORS = {
  free: 'bg-slate-100 text-slate-700',
  pro: 'bg-blue-100 text-blue-700',
  enterprise: 'bg-violet-100 text-violet-700',
}

function BillingBanner({ billing }: { billing: BillingStatus }) {
  const limit = billing.scan_limit
  const used = billing.scan_count_month
  const nearLimit = limit > 0 && used >= limit * 0.8
  return (
    <div className={`rounded-xl border px-4 py-3 flex items-center justify-between gap-4 text-sm ${nearLimit ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-white'}`}>
      <div className="flex items-center gap-3">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${TIER_COLORS[billing.tier]}`}>
          {billing.tier}
        </span>
        <span className="text-slate-500">
          {used} / {limit > 0 ? limit : '∞'} scans this month
        </span>
        {nearLimit && (
          <span className="text-amber-700 font-medium">Nearing limit</span>
        )}
      </div>
      {billing.tier === 'free' && (
        <Link to="/billing" className="text-xs font-semibold text-blue-600 hover:underline shrink-0">
          Upgrade →
        </Link>
      )}
    </div>
  )
}

const STATUS_STYLES: Record<ScanStatus, string> = {
  PENDING: 'bg-amber-50 text-amber-700 border-amber-200',
  PROCESSING: 'bg-blue-50 text-blue-700 border-blue-200',
  COMPLETE: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  FAILED: 'bg-red-50 text-red-700 border-red-200',
  CANCELLED: 'bg-slate-100 text-slate-600 border-slate-300',
}

function CveBadge({ count, label, color }: { count: number | null; label: string; color: string }) {
  if (count === null) return null
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-semibold ${color}`}>
      {count} {label}
    </span>
  )
}

function ScanRow({ scan, onDelete }: { scan: ScanResult; onDelete: (id: string) => void }) {
  const navigate = useNavigate()
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm('Delete this scan?')) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteScan(scan.scan_id)
      onDelete(scan.scan_id)
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Delete failed')
      setDeleting(false)
    }
  }

  const isClickable = scan.status === 'COMPLETE'

  return (
    <tr
      className={`border-b border-slate-100 last:border-0 transition-colors ${isClickable ? 'cursor-pointer hover:bg-slate-50' : ''}`}
      onClick={() => isClickable && navigate(`/v2/results/${scan.scan_id}`)}
    >
      <td className="px-4 py-3">
        <p className="text-sm font-medium text-slate-800 font-mono truncate max-w-xs">
          {scan.scan_type === 'image' ? scan.image_name ?? '—' : 'Dockerfile'}
        </p>
        <p className="text-xs text-slate-400 mt-0.5 capitalize">{scan.scan_type}</p>
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[scan.status]}`}>
          {scan.status}
        </span>
      </td>
      <td className="px-4 py-3 hidden sm:table-cell">
        <div className="flex flex-wrap gap-1">
          <CveBadge count={scan.cve_critical} label="C" color="bg-red-100 text-red-700" />
          <CveBadge count={scan.cve_high} label="H" color="bg-orange-100 text-orange-700" />
          <CveBadge count={scan.cve_medium} label="M" color="bg-amber-100 text-amber-700" />
          <CveBadge count={scan.cve_low} label="L" color="bg-slate-100 text-slate-600" />
          {scan.cve_critical === null && scan.scan_type === 'image' && scan.status !== 'COMPLETE' && (
            <span className="text-xs text-slate-400">—</span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 hidden md:table-cell text-xs text-slate-400">
        {new Date(scan.created_at).toLocaleString()}
      </td>
      <td className="px-4 py-3 text-right">
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="text-xs text-slate-400 hover:text-red-500 transition-colors disabled:opacity-40"
        >
          {deleting ? '…' : 'Delete'}
        </button>
        {deleteError && (
          <p className="text-xs text-red-500 mt-1 max-w-[120px] text-right">{deleteError}</p>
        )}
      </td>
    </tr>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [scans, setScans] = useState<ScanResult[]>([])
  const [nextToken, setNextToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [billing, setBilling] = useState<BillingStatus | null>(null)

  const loadScans = useCallback(async (token?: string) => {
    try {
      const data = await listScans(token)
      setScans(prev => token ? [...prev, ...data.scans] : data.scans)
      setNextToken(data.next_page_token)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scans.')
    }
  }, [])

  useEffect(() => {
    loadScans().finally(() => setLoading(false))
    getBillingStatus().then(setBilling).catch(() => null)
  }, [loadScans])

  async function handleLoadMore() {
    if (!nextToken) return
    setLoadingMore(true)
    await loadScans(nextToken)
    setLoadingMore(false)
  }

  function handleDelete(scanId: string) {
    setScans(prev => prev.filter(s => s.scan_id !== scanId))
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <NavBar />
      <main className="flex-1 mx-auto w-full max-w-4xl px-4 py-10">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">Dashboard</h2>
            <p className="text-sm text-slate-500 mt-0.5">{user?.email}</p>
          </div>
          <button
            onClick={() => navigate('/')}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            + New scan
          </button>
        </div>

        {billing && <div className="mb-6"><BillingBanner billing={billing} /></div>}

        {loading ? (
          <LoadingSpinner message="Loading your scans…" />
        ) : error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">{error}</div>
        ) : scans.length === 0 ? (
          <div className="rounded-xl border-2 border-dashed border-slate-200 bg-white p-12 text-center">
            <p className="text-slate-500 font-medium">No scans yet.</p>
            <p className="text-sm text-slate-400 mt-1">Submit a Dockerfile or image name to get started.</p>
            <button
              onClick={() => navigate('/')}
              className="mt-4 text-sm text-blue-600 hover:underline"
            >
              Go to analyzer
            </button>
          </div>
        ) : (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Target</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 hidden sm:table-cell">CVEs</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 hidden md:table-cell">Date</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {scans.map(scan => (
                  <ScanRow key={scan.scan_id} scan={scan} onDelete={handleDelete} />
                ))}
              </tbody>
            </table>

            {nextToken && (
              <div className="px-4 py-4 border-t border-slate-100 text-center">
                <button
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="text-sm font-medium text-blue-600 hover:underline disabled:opacity-40"
                >
                  {loadingMore ? 'Loading…' : 'Load more'}
                </button>
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="py-6 text-center text-xs text-slate-400">
        Docker & Kubernetes Analyzer &mdash; Phase 3
      </footer>
    </div>
  )
}
