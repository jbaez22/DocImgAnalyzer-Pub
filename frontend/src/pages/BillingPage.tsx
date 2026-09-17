import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { createCheckoutSession, createPortalSession, getBillingStatus } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'
import NavBar from '../components/NavBar'
import type { BillingStatus, SubscriptionTier } from '../types/api'

const PRO_PRICE_ID = import.meta.env.VITE_STRIPE_PRO_PRICE_ID as string
const ENTERPRISE_PRICE_ID = import.meta.env.VITE_STRIPE_ENTERPRISE_PRICE_ID as string

const TIER_LABELS: Record<SubscriptionTier, string> = {
  free: 'Free',
  pro: 'Pro',
  enterprise: 'Enterprise',
}

const TIER_COLORS: Record<SubscriptionTier, string> = {
  free: 'bg-slate-100 text-slate-700',
  pro: 'bg-blue-100 text-blue-700',
  enterprise: 'bg-violet-100 text-violet-700',
}

function UsageBar({ used, limit }: { used: number; limit: number }) {
  const pct = limit <= 0 ? 0 : Math.min(100, Math.round((used / limit) * 100))
  const color = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-blue-500'
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs text-slate-500">
        <span>{used} scans used this month</span>
        <span>{limit > 0 ? `${limit} limit` : 'Unlimited'}</span>
      </div>
      {limit > 0 && (
        <div className="h-2 w-full rounded-full bg-slate-100">
          <div className={`h-2 rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  )
}

interface PlanCardProps {
  name: string
  price: string
  features: string[]
  priceId: string | null
  current: boolean
  onUpgrade: (priceId: string) => void
  loading: boolean
}

function PlanCard({ name, price, features, priceId, current, onUpgrade, loading }: PlanCardProps) {
  return (
    <div className={`rounded-2xl border p-6 flex flex-col gap-4 ${current ? 'border-blue-400 bg-blue-50' : 'border-slate-200 bg-white'}`}>
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-900">{name}</h3>
        {current && (
          <span className="rounded-full bg-blue-600 px-2.5 py-0.5 text-xs font-semibold text-white">
            Current plan
          </span>
        )}
      </div>
      <p className="text-2xl font-bold text-slate-900">
        {price} <span className="text-sm font-normal text-slate-500">/ month</span>
      </p>
      <ul className="space-y-2 text-sm text-slate-600 flex-1">
        {features.map(f => (
          <li key={f} className="flex items-center gap-2">
            <span className="text-emerald-500 font-bold">✓</span> {f}
          </li>
        ))}
      </ul>
      {!current && priceId && (
        <button
          onClick={() => onUpgrade(priceId)}
          disabled={loading}
          className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {loading ? 'Redirecting…' : `Upgrade to ${name}`}
        </button>
      )}
    </div>
  )
}

export default function BillingPage() {
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState<BillingStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const [portalLoading, setPortalLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sessionSuccess = searchParams.get('session_id') !== null

  useEffect(() => {
    getBillingStatus()
      .then(setStatus)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load billing info.'))
      .finally(() => setLoading(false))
  }, [])

  async function handleUpgrade(priceId: string) {
    setCheckoutLoading(true)
    try {
      const { checkout_url } = await createCheckoutSession(priceId)
      window.location.href = checkout_url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start checkout.')
      setCheckoutLoading(false)
    }
  }

  async function handlePortal() {
    setPortalLoading(true)
    try {
      const { portal_url } = await createPortalSession()
      window.location.href = portal_url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open billing portal.')
      setPortalLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <NavBar />
      <main className="flex-1 mx-auto w-full max-w-4xl px-4 py-10">
        <h2 className="text-2xl font-bold text-slate-900 mb-1">Billing</h2>
        <p className="text-sm text-slate-500 mb-8">Manage your plan and usage.</p>

        {sessionSuccess && (
          <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-800">
            Subscription activated — thank you! Your plan has been updated.
          </div>
        )}

        {error && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading ? (
          <LoadingSpinner message="Loading billing info…" />
        ) : status ? (
          <div className="space-y-8">
            {/* Current status card */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 space-y-4">
              <div className="flex items-center gap-3">
                <span className={`rounded-full px-3 py-1 text-sm font-semibold ${TIER_COLORS[status.tier]}`}>
                  {TIER_LABELS[status.tier]}
                </span>
                {status.payment_past_due && (
                  <span className="rounded-full bg-red-100 px-3 py-1 text-sm font-semibold text-red-700">
                    Payment past due
                  </span>
                )}
              </div>

              <UsageBar
                used={status.scan_count_month}
                limit={status.scan_limit}
              />

              {status.period_end && (
                <p className="text-xs text-slate-400">
                  Renews {new Date(status.period_end).toLocaleDateString()}
                </p>
              )}

              {status.tier !== 'free' && (
                <button
                  onClick={handlePortal}
                  disabled={portalLoading}
                  className="text-sm font-medium text-blue-600 hover:underline disabled:opacity-50"
                >
                  {portalLoading ? 'Opening portal…' : 'Manage billing & invoices →'}
                </button>
              )}
            </div>

            {/* Plan comparison */}
            <div className="grid gap-4 sm:grid-cols-3">
              <PlanCard
                name="Free"
                price="$0"
                features={['10 scans / month', 'Dockerfile analysis', 'Score & findings']}
                priceId={null}
                current={status.tier === 'free'}
                onUpgrade={handleUpgrade}
                loading={checkoutLoading}
              />
              <PlanCard
                name="Pro"
                price="$19"
                features={['200 scans / month', 'Dockerfile + image scans', 'CVE reports & SBOM', 'API key access']}
                priceId={PRO_PRICE_ID}
                current={status.tier === 'pro'}
                onUpgrade={handleUpgrade}
                loading={checkoutLoading}
              />
              <PlanCard
                name="Enterprise"
                price="$99"
                features={['Unlimited scans', 'Everything in Pro', 'Team / org management', 'Priority support']}
                priceId={ENTERPRISE_PRICE_ID}
                current={status.tier === 'enterprise'}
                onUpgrade={handleUpgrade}
                loading={checkoutLoading}
              />
            </div>
          </div>
        ) : null}
      </main>

      <footer className="py-6 text-center text-xs text-slate-400">
        Docker & Kubernetes Analyzer &mdash; Phase 3
      </footer>
    </div>
  )
}
