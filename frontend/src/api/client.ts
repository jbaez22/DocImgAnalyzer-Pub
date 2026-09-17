import { getIdToken } from '../auth/useAuth'
import type {
  AnalysisReport,
  ApiKeyCreateResponse,
  ApiKeyListResponse,
  BillingStatus,
  CheckoutResponse,
  DockerfileAnalyzeRequest,
  DockerfileAnalyzeResponse,
  ImageAnalyzeRequest,
  ImageScanRequest,
  ImageScanSubmitResponse,
  KubernetesAnalyzeRequest,
  PortalResponse,
  ScanListResponse,
  ScanResult,
  V3DockerfileAnalyzeResponse,
} from '../types/api'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

// ── v1 (unauthenticated) ──────────────────────────────────────────────────────

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error((error as { detail?: string }).detail ?? `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function analyzeDockerfile(payload: DockerfileAnalyzeRequest): Promise<AnalysisReport> {
  return request<AnalysisReport>('/api/v1/analyze/dockerfile', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function analyzeImage(payload: ImageAnalyzeRequest): Promise<AnalysisReport> {
  return request<AnalysisReport>('/api/v1/analyze/image', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function analyzeKubernetes(
  payload: KubernetesAnalyzeRequest,
): Promise<AnalysisReport> {
  return request<AnalysisReport>('/api/v1/analyze/kubernetes', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getResult(scanId: string): Promise<AnalysisReport> {
  return request<AnalysisReport>(`/api/v1/results/${scanId}`)
}

// ── v2 (JWT-authenticated) ────────────────────────────────────────────────────

async function requestV2<T>(path: string, options?: RequestInit): Promise<T> {
  const token = await getIdToken()
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error((error as { detail?: string }).detail ?? `Request failed: ${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function analyzeDockerfileV2(
  payload: DockerfileAnalyzeRequest,
): Promise<DockerfileAnalyzeResponse> {
  return requestV2<DockerfileAnalyzeResponse>('/api/v2/analyze/dockerfile', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function analyzeImageV2(payload: ImageScanRequest): Promise<ImageScanSubmitResponse> {
  return requestV2<ImageScanSubmitResponse>('/api/v2/analyze/image', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function analyzeKubernetesV2(
  payload: KubernetesAnalyzeRequest,
): Promise<DockerfileAnalyzeResponse> {
  return requestV2<DockerfileAnalyzeResponse>('/api/v2/analyze/kubernetes', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getResultV2(scanId: string): Promise<ScanResult> {
  return requestV2<ScanResult>(`/api/v2/results/${scanId}`)
}

export function listScans(nextToken?: string): Promise<ScanListResponse> {
  const qs = nextToken ? `?next_token=${encodeURIComponent(nextToken)}` : ''
  return requestV2<ScanListResponse>(`/api/v2/scans${qs}`)
}

export function deleteScan(scanId: string): Promise<void> {
  return requestV2<void>(`/api/v2/scans/${scanId}`, { method: 'DELETE' })
}

export function cancelScan(scanId: string): Promise<void> {
  return requestV2<void>(`/api/v2/scans/${scanId}/cancel`, { method: 'POST' })
}

// ── v3 (JWT-authenticated — same auth pattern as v2) ─────────────────────────

async function requestV3<T>(path: string, options?: RequestInit): Promise<T> {
  const token = await getIdToken()
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error((error as { detail?: string }).detail ?? `Request failed: ${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function analyzeDockerfileV3(
  payload: DockerfileAnalyzeRequest,
): Promise<V3DockerfileAnalyzeResponse> {
  return requestV3<V3DockerfileAnalyzeResponse>('/api/v3/analyze/dockerfile', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getBillingStatus(): Promise<BillingStatus> {
  return requestV3<BillingStatus>('/api/v3/billing/status')
}

export function createCheckoutSession(priceId: string): Promise<CheckoutResponse> {
  return requestV3<CheckoutResponse>('/api/v3/billing/checkout', {
    method: 'POST',
    body: JSON.stringify({ price_id: priceId }),
  })
}

export function createPortalSession(): Promise<PortalResponse> {
  return requestV3<PortalResponse>('/api/v3/billing/portal', { method: 'POST' })
}

export function listApiKeys(): Promise<ApiKeyListResponse> {
  return requestV3<ApiKeyListResponse>('/api/v3/keys')
}

export function createApiKey(name: string): Promise<ApiKeyCreateResponse> {
  return requestV3<ApiKeyCreateResponse>('/api/v3/keys', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export function revokeApiKey(keyId: string): Promise<void> {
  return requestV3<void>(`/api/v3/keys/${keyId}`, { method: 'DELETE' })
}
