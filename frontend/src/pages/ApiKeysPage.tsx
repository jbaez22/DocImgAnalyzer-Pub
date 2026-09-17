import { useEffect, useRef, useState } from 'react'
import { createApiKey, listApiKeys, revokeApiKey } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'
import NavBar from '../components/NavBar'
import type { ApiKeySummary } from '../types/api'

function NewKeyModal({ rawKey, onClose }: { rawKey: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    await navigator.clipboard.writeText(rawKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl space-y-4">
        <h3 className="text-lg font-bold text-slate-900">API Key Created</h3>
        <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
          Copy this key now — it will not be shown again.
        </p>
        <div className="flex items-center gap-2">
          <code className="flex-1 rounded-lg bg-slate-100 px-3 py-2 text-xs font-mono text-slate-800 break-all">
            {rawKey}
          </code>
          <button
            onClick={handleCopy}
            className="shrink-0 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <button
          onClick={onClose}
          className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
        >
          Done
        </button>
      </div>
    </div>
  )
}

function KeyRow({ k, onRevoke }: { k: ApiKeySummary; onRevoke: (id: string) => void }) {
  const [revoking, setRevoking] = useState(false)

  async function handleRevoke() {
    if (!confirm(`Revoke key "${k.name}"? This cannot be undone.`)) return
    setRevoking(true)
    try {
      await revokeApiKey(k.key_id)
      onRevoke(k.key_id)
    } catch {
      setRevoking(false)
    }
  }

  return (
    <tr className="border-b border-slate-100 last:border-0">
      <td className="px-4 py-3">
        <p className="text-sm font-medium text-slate-800">{k.name}</p>
        <p className="text-xs text-slate-400 font-mono mt-0.5">dia_••••••••</p>
      </td>
      <td className="px-4 py-3 hidden sm:table-cell text-xs text-slate-400">
        {new Date(k.created_at).toLocaleDateString()}
      </td>
      <td className="px-4 py-3 hidden md:table-cell text-xs text-slate-400">
        {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : '—'}
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${k.revoked ? 'bg-red-50 text-red-600 border-red-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200'}`}>
          {k.revoked ? 'Revoked' : 'Active'}
        </span>
      </td>
      <td className="px-4 py-3 text-right">
        {!k.revoked && (
          <button
            onClick={handleRevoke}
            disabled={revoking}
            className="text-xs text-slate-400 hover:text-red-500 transition-colors disabled:opacity-40"
          >
            {revoking ? '…' : 'Revoke'}
          </button>
        )}
      </td>
    </tr>
  )
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeySummary[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newRawKey, setNewRawKey] = useState<string | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listApiKeys()
      .then(data => setKeys(data.keys))
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load keys.'))
      .finally(() => setLoading(false))
  }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    const name = nameRef.current?.value.trim()
    if (!name) return
    setCreating(true)
    setError(null)
    try {
      const result = await createApiKey(name)
      setKeys(prev => [
        { key_id: result.key_id, name: result.name, created_at: result.created_at, last_used_at: null, revoked: false },
        ...prev,
      ])
      setNewRawKey(result.raw_key)
      if (nameRef.current) nameRef.current.value = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create key.')
    } finally {
      setCreating(false)
    }
  }

  function handleRevoke(keyId: string) {
    setKeys(prev => prev.map(k => k.key_id === keyId ? { ...k, revoked: true } : k))
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <NavBar />

      {newRawKey && (
        <NewKeyModal rawKey={newRawKey} onClose={() => setNewRawKey(null)} />
      )}

      <main className="flex-1 mx-auto w-full max-w-4xl px-4 py-10">
        <h2 className="text-2xl font-bold text-slate-900 mb-1">API Keys</h2>
        <p className="text-sm text-slate-500 mb-8">
          Use <code className="font-mono text-xs bg-slate-100 px-1 py-0.5 rounded">X-Api-Key: dia_…</code> to authenticate programmatic requests.
        </p>

        {error && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Create key form */}
        <form onSubmit={handleCreate} className="mb-8 rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Create new key</h3>
          <div className="flex gap-3">
            <input
              ref={nameRef}
              type="text"
              placeholder="Key name (e.g. CI pipeline)"
              maxLength={64}
              required
              className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>

        {/* Key list */}
        {loading ? (
          <LoadingSpinner message="Loading keys…" />
        ) : keys.length === 0 ? (
          <div className="rounded-xl border-2 border-dashed border-slate-200 bg-white p-10 text-center">
            <p className="text-slate-500 font-medium">No API keys yet.</p>
            <p className="text-sm text-slate-400 mt-1">Create one above to start using the API programmatically.</p>
          </div>
        ) : (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 hidden sm:table-cell">Created</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 hidden md:table-cell">Last used</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {keys.map(k => (
                  <KeyRow key={k.key_id} k={k} onRevoke={handleRevoke} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      <footer className="py-6 text-center text-xs text-slate-400">
        Docker & Kubernetes Analyzer &mdash; Phase 3
      </footer>
    </div>
  )
}
