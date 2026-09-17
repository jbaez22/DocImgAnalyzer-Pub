export type ScanType = 'dockerfile' | 'image' | 'kubernetes'
export type ScanStatus = 'PENDING' | 'PROCESSING' | 'COMPLETE' | 'FAILED' | 'CANCELLED'
export type Severity = 'INFO' | 'WARNING' | 'ERROR'

export interface Finding {
  rule_id: string
  severity: Severity
  title: string
  description: string
  fix: string | null
  line: number | null
}

export interface AnalysisReport {
  scan_id: string
  scan_type: ScanType
  status: ScanStatus
  score: number | null
  findings: Finding[]
  fixed_dockerfile: string | null
  metadata: Record<string, unknown>
  created_at: string
  completed_at: string | null
}

export interface DockerfileAnalyzeRequest {
  content: string
}

export interface ImageAnalyzeRequest {
  image: string
}

export interface KubernetesAnalyzeRequest {
  content: string
}

export interface ApiError {
  detail: string
}

// ── v2 types ──────────────────────────────────────────────────────────────────

export interface DockerfileAnalyzeResponse {
  scan_id: string
  score: number
  findings: Finding[]
  fixed_dockerfile: string
  created_at: string
}

export interface ImageScanRequest {
  image_name: string
}

export interface ImageScanSubmitResponse {
  scan_id: string
}

export interface ScanResult {
  scan_id: string
  scan_type: ScanType
  status: ScanStatus
  image_name: string | null
  created_at: string
  // image scan fields
  cve_critical: number | null
  cve_high: number | null
  cve_medium: number | null
  cve_low: number | null
  report_url: string | null
  sbom_url: string | null
  // dockerfile scan fields
  score: number | null
  findings: Finding[] | null
  fixed_dockerfile: string | null
}

export interface ScanListResponse {
  scans: ScanResult[]
  next_page_token: string | null
}

// ── v3 types ──────────────────────────────────────────────────────────────────

export type SubscriptionTier = 'free' | 'pro' | 'enterprise'

export interface BillingStatus {
  tier: SubscriptionTier
  scan_count_month: number
  scan_limit: number
  period_end: string | null
  payment_past_due: boolean
}

export interface CheckoutResponse {
  checkout_url: string
}

export interface PortalResponse {
  portal_url: string
}

export interface ApiKeySummary {
  key_id: string
  name: string
  created_at: string
  last_used_at: string | null
  revoked: boolean
}

export interface ApiKeyListResponse {
  keys: ApiKeySummary[]
}

export interface ApiKeyCreateResponse {
  key_id: string
  name: string
  raw_key: string
  created_at: string
}

export interface V3DockerfileAnalyzeResponse {
  scan_id: string
  score: number
  findings: Finding[]
  fixed_dockerfile: string
  created_at: string
}
