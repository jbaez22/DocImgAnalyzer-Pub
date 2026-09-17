import { useEffect, useState } from 'react'

interface TrivyVuln {
  VulnerabilityID: string
  PkgName: string
  InstalledVersion: string
  FixedVersion?: string
  Severity: CveSeverity
  Title?: string
  Description?: string
}

interface TrivyResult {
  Target: string
  Type: string
  Vulnerabilities?: TrivyVuln[]
}

interface TrivyReport {
  Results?: TrivyResult[]
}

type CveSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN'

const SEVERITY_ORDER: CveSeverity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']

const SEVERITY_STYLE: Record<CveSeverity, { badge: string; border: string; section: string }> = {
  CRITICAL: {
    badge: 'bg-red-100 text-red-800 border border-red-300',
    border: 'border-l-red-600',
    section: 'border-red-200 bg-red-50',
  },
  HIGH: {
    badge: 'bg-orange-100 text-orange-800 border border-orange-300',
    border: 'border-l-orange-500',
    section: 'border-orange-200 bg-orange-50',
  },
  MEDIUM: {
    badge: 'bg-amber-100 text-amber-800 border border-amber-300',
    border: 'border-l-amber-400',
    section: 'border-amber-200 bg-amber-50',
  },
  LOW: {
    badge: 'bg-slate-100 text-slate-700 border border-slate-300',
    border: 'border-l-slate-400',
    section: 'border-slate-200 bg-slate-50',
  },
  UNKNOWN: {
    badge: 'bg-gray-100 text-gray-700 border border-gray-300',
    border: 'border-l-gray-400',
    section: 'border-gray-200 bg-gray-50',
  },
}

// ── OS packages that Alpine eliminates ────────────────────────────────────────
const OS_PKG_PREFIXES = [
  'libc6', 'libssl', 'openssl', 'zlib1g', 'libgcc-s1', 'libstdc++6',
  'libsystemd0', 'libudev1', 'libpcre3', 'libexpat1', 'libgcrypt20',
  'libgnutls30', 'libp11-kit0', 'libcurl', 'libpng', 'libtiff',
  'libwebp', 'libxml2', 'libxslt', 'libsqlite3',
]

// Base images that have a direct -alpine variant on Docker Hub
const ALPINE_CAPABLE = ['python', 'node', 'ruby', 'golang', 'nginx', 'php', 'java', 'openjdk']

interface PackageUpgrade {
  pkg: string
  from: string
  to: string
}

function deriveUpgrades(vulns: TrivyVuln[]): PackageUpgrade[] {
  const seen = new Map<string, PackageUpgrade>()
  for (const v of vulns) {
    if (!v.FixedVersion || v.FixedVersion === '') continue
    const key = `${v.PkgName}@@${v.InstalledVersion}`
    if (!seen.has(key)) {
      seen.set(key, { pkg: v.PkgName, from: v.InstalledVersion, to: v.FixedVersion })
    }
  }
  return [...seen.values()].sort((a, b) => a.pkg.localeCompare(b.pkg))
}

function deriveBaseImageSuggestion(
  imageName: string | null | undefined,
  vulns: TrivyVuln[],
): string | null {
  const osVulns = vulns.filter(v => OS_PKG_PREFIXES.some(p => v.PkgName.startsWith(p)))
  if (osVulns.length < 3) return null

  if (!imageName) return null

  const lower = imageName.toLowerCase()
  // Already on alpine — no suggestion needed
  if (lower.includes('alpine') || lower.includes('distroless') || lower.includes('chainguard')) {
    return null
  }

  // Extract repo and tag: "python:3.12-slim" → repo="python", tag="3.12-slim"
  const colonIdx = imageName.indexOf(':')
  const repo = colonIdx === -1 ? imageName : imageName.slice(0, colonIdx)
  const tag = colonIdx === -1 ? 'latest' : imageName.slice(colonIdx + 1)
  const repoBase = repo.split('/').pop() ?? repo   // strip registry prefix

  // Strip known Debian/Ubuntu suffixes to get the version part
  const cleanTag = tag
    .replace(/-(slim|bullseye|buster|bookworm|stretch|focal|jammy|bionic|noble)$/, '')

  if (ALPINE_CAPABLE.some(r => repoBase.startsWith(r))) {
    return `FROM ${repo}:${cleanTag}-alpine`
  }

  return null
}

function deriveRecommendations(vulns: TrivyVuln[]): string[] {
  if (vulns.length === 0) return []
  const recs: string[] = []
  const fixable = vulns.filter(v => v.FixedVersion && v.FixedVersion !== '')
  const critical = vulns.filter(v => v.Severity === 'CRITICAL')
  const high = vulns.filter(v => v.Severity === 'HIGH')

  if (fixable.length > 0) {
    recs.push(
      `${fixable.length} of ${vulns.length} vulnerabilities have a fix available — upgrade these packages to resolve them.`,
    )
  }
  if (critical.length > 0 || high.length > 0) {
    const urgentPkgs = [...new Set([...critical, ...high].map(v => v.PkgName))].slice(0, 5)
    recs.push(
      `Prioritize upgrading: ${urgentPkgs.join(', ')} — these contain CRITICAL or HIGH severity CVEs.`,
    )
  }
  const osVulns = vulns.filter(v => OS_PKG_PREFIXES.some(p => v.PkgName.startsWith(p)))
  if (osVulns.length >= 3) {
    recs.push(
      `${osVulns.length} vulnerabilities are in OS-level packages. Switching to an Alpine-based image would eliminate most of these (see Remediation below).`,
    )
  }
  const unfixable = vulns.filter(v => !v.FixedVersion || v.FixedVersion === '')
  if (unfixable.length > 0 && unfixable.length === vulns.length) {
    recs.push('None of the detected vulnerabilities have upstream fixes yet — monitor for new releases.')
  }
  return recs
}

// ── Remediation panel ─────────────────────────────────────────────────────────

interface RemediationProps {
  upgrades: PackageUpgrade[]
  baseImageSuggestion: string | null
}

function Remediation({ upgrades, baseImageSuggestion }: RemediationProps) {
  if (upgrades.length === 0 && !baseImageSuggestion) return null

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-900 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700">
        <span className="text-xs font-semibold text-slate-300 uppercase tracking-wide">
          Remediation
        </span>
        <span className="text-xs text-emerald-400">
          {upgrades.length} package{upgrades.length !== 1 ? 's' : ''} fixable
        </span>
      </div>

      <div className="px-4 py-4 space-y-5">
        {/* Package upgrades */}
        {upgrades.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
              Package Upgrades
            </p>
            <div className="space-y-1 max-h-64 overflow-y-auto pr-1">
              {upgrades.map((u, i) => (
                <div key={i} className="flex items-baseline gap-2 font-mono text-xs leading-relaxed">
                  <span className="text-slate-200 shrink-0">{u.pkg}</span>
                  <span className="text-slate-500 shrink-0">{u.from}</span>
                  <span className="text-slate-500 shrink-0">→</span>
                  <span className="text-emerald-400 shrink-0">{u.to}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Base image suggestion */}
        {baseImageSuggestion && (
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
              Base Image — switch to Alpine to eliminate OS-level CVEs
            </p>
            <pre className="text-xs text-sky-300 leading-relaxed whitespace-pre">
              {baseImageSuggestion}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}

// ── CVE row ───────────────────────────────────────────────────────────────────

function CveRow({ vuln }: { vuln: TrivyVuln }) {
  const [expanded, setExpanded] = useState(false)
  const style = SEVERITY_STYLE[vuln.Severity] ?? SEVERITY_STYLE.UNKNOWN
  const hasDescription = Boolean(vuln.Description)

  return (
    <div className={`rounded-lg border border-slate-200 bg-white border-l-4 ${style.border} overflow-hidden`}>
      <div
        className={`flex items-start gap-3 px-4 py-3 ${hasDescription ? 'cursor-pointer hover:bg-slate-50' : ''}`}
        onClick={() => hasDescription && setExpanded(e => !e)}
      >
        <span className={`shrink-0 rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${style.badge}`}>
          {vuln.Severity}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-800 truncate">{vuln.VulnerabilityID}</p>
          <p className="text-xs text-slate-500 mt-0.5">
            <span className="font-mono">{vuln.PkgName}@{vuln.InstalledVersion}</span>
            {' '}
            {vuln.FixedVersion
              ? <span className="text-emerald-600">→ fix: {vuln.FixedVersion}</span>
              : <span className="text-slate-400">no fix available</span>
            }
          </p>
          {vuln.Title && (
            <p className="text-xs text-slate-600 mt-1 leading-relaxed">{vuln.Title}</p>
          )}
        </div>
        {hasDescription && (
          <span className="shrink-0 text-slate-400 text-xs mt-1">{expanded ? '▲' : '▼'}</span>
        )}
      </div>
      {expanded && vuln.Description && (
        <div className="px-4 pb-3 border-t border-slate-100 bg-slate-50">
          <p className="text-xs text-slate-600 leading-relaxed pt-2">{vuln.Description}</p>
        </div>
      )}
    </div>
  )
}

// ── Severity group ────────────────────────────────────────────────────────────

function SeverityGroup({ severity, vulns, defaultOpen }: {
  severity: CveSeverity
  vulns: TrivyVuln[]
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const style = SEVERITY_STYLE[severity] ?? SEVERITY_STYLE.UNKNOWN

  return (
    <div className={`rounded-xl border ${style.section} overflow-hidden`}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:brightness-95 transition-all"
      >
        <div className="flex items-center gap-2">
          <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${style.badge}`}>
            {severity}
          </span>
          <span className="text-sm font-semibold text-slate-700">
            {vulns.length} {vulns.length === 1 ? 'vulnerability' : 'vulnerabilities'}
          </span>
        </div>
        <span className="text-slate-500 text-xs">{open ? '▲ collapse' : '▼ expand'}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-2">
          {vulns.map((v, i) => (
            <CveRow key={`${v.VulnerabilityID}-${i}`} vuln={v} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

interface Props {
  reportUrl: string | null
  imageName?: string | null
}

export default function CveFindings({ reportUrl, imageName }: Props) {
  const [vulns, setVulns] = useState<TrivyVuln[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!reportUrl) return
    let cancelled = false
    setLoading(true)
    setLoadError(null)

    fetch(reportUrl)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<TrivyReport>
      })
      .then(data => {
        if (cancelled) return
        const all: TrivyVuln[] = []
        for (const result of data.Results ?? []) {
          for (const v of result.Vulnerabilities ?? []) {
            all.push(v)
          }
        }
        setVulns(all)
      })
      .catch(err => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load report')
      })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [reportUrl])

  if (!reportUrl) return null
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500 py-4">
        <div className="h-4 w-4 rounded-full border-2 border-slate-400 border-t-transparent animate-spin" />
        Loading vulnerability details…
      </div>
    )
  }
  if (loadError) {
    return <p className="text-sm text-red-500 py-2">Could not load vulnerability details: {loadError}</p>
  }
  if (!vulns || vulns.length === 0) {
    return (
      <div className="rounded-xl border-2 border-dashed border-emerald-200 bg-emerald-50 p-6 text-center">
        <p className="text-emerald-700 font-semibold">No vulnerabilities found in the report.</p>
      </div>
    )
  }

  const grouped = SEVERITY_ORDER.reduce<Record<CveSeverity, TrivyVuln[]>>((acc, s) => {
    acc[s] = vulns.filter(v => v.Severity === s)
    return acc
  }, { CRITICAL: [], HIGH: [], MEDIUM: [], LOW: [], UNKNOWN: [] })

  const recommendations = deriveRecommendations(vulns)
  const upgrades = deriveUpgrades(vulns)
  const baseImageSuggestion = deriveBaseImageSuggestion(imageName, vulns)

  return (
    <div className="space-y-4">
      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 px-5 py-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-blue-700 mb-2">
            Recommendations
          </h4>
          <ul className="space-y-1.5">
            {recommendations.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-blue-900">
                <span className="mt-0.5 shrink-0 text-blue-400">•</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Remediation */}
      <Remediation upgrades={upgrades} baseImageSuggestion={baseImageSuggestion} />

      {/* Vulnerability details by severity */}
      <div className="space-y-3">
        {SEVERITY_ORDER.filter(s => grouped[s].length > 0).map(s => (
          <SeverityGroup
            key={s}
            severity={s}
            vulns={grouped[s]}
            defaultOpen={s === 'CRITICAL' || s === 'HIGH'}
          />
        ))}
      </div>
    </div>
  )
}
