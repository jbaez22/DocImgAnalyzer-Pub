import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  analyzeDockerfile,
  analyzeDockerfileV2,
  analyzeImage,
  analyzeImageV2,
  analyzeKubernetes,
  analyzeKubernetesV2,
} from '../api/client'
import { useAuth } from '../auth/useAuth'
import LoadingSpinner from '../components/LoadingSpinner'
import NavBar from '../components/NavBar'

type Tab = 'dockerfile' | 'image' | 'kubernetes'

export default function HomePage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const isAuthenticated = !!user

  const [activeTab, setActiveTab] = useState<Tab>('dockerfile')
  const [dockerfileContent, setDockerfileContent] = useState('')
  const [imageName, setImageName] = useState('')
  const [manifestContent, setManifestContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleDockerfileSubmit(e: FormEvent) {
    e.preventDefault()
    if (!dockerfileContent.trim()) return
    setLoading(true)
    setError(null)
    try {
      if (isAuthenticated) {
        const res = await analyzeDockerfileV2({ content: dockerfileContent })
        navigate(`/results/${res.scan_id}`, {
          state: {
            report: {
              ...res,
              scan_type: 'dockerfile' as const,
              status: 'COMPLETE' as const,
              metadata: {},
              completed_at: null,
            },
          },
        })
      } else {
        const report = await analyzeDockerfile({ content: dockerfileContent })
        navigate(`/results/${report.scan_id}`, { state: { report } })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.')
    } finally {
      setLoading(false)
    }
  }

  async function handleManifestSubmit(e: FormEvent) {
    e.preventDefault()
    if (!manifestContent.trim()) return
    setLoading(true)
    setError(null)
    try {
      if (isAuthenticated) {
        const res = await analyzeKubernetesV2({ content: manifestContent })
        navigate(`/results/${res.scan_id}`, {
          state: {
            report: {
              ...res,
              scan_type: 'kubernetes' as const,
              status: 'COMPLETE' as const,
              metadata: {},
              completed_at: null,
            },
          },
        })
      } else {
        const report = await analyzeKubernetes({ content: manifestContent })
        navigate(`/results/${report.scan_id}`, { state: { report } })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.')
    } finally {
      setLoading(false)
    }
  }

  async function handleImageSubmit(e: FormEvent) {
    e.preventDefault()
    if (!imageName.trim()) return
    setLoading(true)
    setError(null)
    try {
      if (isAuthenticated) {
        const res = await analyzeImageV2({ image_name: imageName.trim() })
        navigate(`/v2/results/${res.scan_id}`)
      } else {
        const report = await analyzeImage({ image: imageName.trim() })
        navigate(`/results/${report.scan_id}`, { state: { report } })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <NavBar />

      {/* Main */}
      <main className="flex-1 mx-auto w-full max-w-4xl px-4 py-12">
        <div className="text-center mb-10">
          <h2 className="text-3xl font-bold text-slate-900">Analyze your Docker &amp; Kubernetes assets</h2>
          <p className="mt-3 text-slate-500 max-w-xl mx-auto">
            Submit a Dockerfile or Kubernetes manifest to get a security score and
            best-practice findings, or enter an image name to inspect its metadata from
            Docker Hub.
          </p>
          {!isAuthenticated && (
            <p className="mt-3 text-sm text-slate-500 max-w-xl mx-auto">
              Create a free account to unlock full CVE scans of your publicly accessible Docker
              image and save your results to your dashboard. Click{' '}
              <span className="font-semibold text-blue-600">Sign in</span> in the top-right
              corner to get started.
            </p>
          )}
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="flex border-b border-slate-200">
            <button
              onClick={() => setActiveTab('dockerfile')}
              className={`flex-1 py-4 text-sm font-semibold transition-colors ${
                activeTab === 'dockerfile'
                  ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-600'
                  : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
              }`}
            >
              Dockerfile Analysis
            </button>
            <button
              onClick={() => setActiveTab('kubernetes')}
              className={`flex-1 py-4 text-sm font-semibold transition-colors ${
                activeTab === 'kubernetes'
                  ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-600'
                  : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
              }`}
            >
              Kubernetes Manifest
            </button>
            <button
              onClick={() => setActiveTab('image')}
              className={`flex-1 py-4 text-sm font-semibold transition-colors ${
                activeTab === 'image'
                  ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-600'
                  : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
              }`}
            >
              {isAuthenticated ? 'CVE Image Scan' : 'Image Metadata'}
            </button>
          </div>

          <div className="p-6">
            {loading ? (
              <LoadingSpinner message={
                activeTab === 'dockerfile'
                  ? 'Analysing Dockerfile…'
                  : activeTab === 'kubernetes'
                    ? 'Analysing Kubernetes manifest…'
                    : isAuthenticated
                      ? 'Submitting image for CVE scan…'
                      : 'Fetching image metadata…'
              } />
            ) : (
              <>
                {activeTab === 'dockerfile' && (
                  <form onSubmit={handleDockerfileSubmit} className="space-y-4">
                    <div>
                      <label htmlFor="dockerfile" className="block text-sm font-medium text-slate-700 mb-1.5">
                        Paste your Dockerfile
                      </label>
                      <textarea
                        id="dockerfile"
                        value={dockerfileContent}
                        onChange={e => setDockerfileContent(e.target.value)}
                        rows={14}
                        placeholder={`FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nUSER 1000\nCMD ["python", "main.py"]`}
                        className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 font-mono text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 resize-y"
                        required
                      />
                      <p className="mt-1 text-xs text-slate-400">Max 512 KB</p>
                    </div>
                    <button
                      type="submit"
                      disabled={!dockerfileContent.trim()}
                      className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      Analyse Dockerfile
                    </button>
                  </form>
                )}

                {activeTab === 'kubernetes' && (
                  <form onSubmit={handleManifestSubmit} className="space-y-4">
                    <div>
                      <label htmlFor="manifest" className="block text-sm font-medium text-slate-700 mb-1.5">
                        Paste your Kubernetes manifest
                      </label>
                      <textarea
                        id="manifest"
                        value={manifestContent}
                        onChange={e => setManifestContent(e.target.value)}
                        rows={14}
                        placeholder={`apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web-app\nspec:\n  template:\n    spec:\n      containers:\n        - name: web\n          image: nginx:1.29-alpine`}
                        className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 font-mono text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 resize-y"
                        required
                      />
                      <p className="mt-1 text-xs text-slate-400">
                        Supports Pod, Deployment, StatefulSet, DaemonSet, Job, ReplicaSet, CronJob
                      </p>
                    </div>
                    <button
                      type="submit"
                      disabled={!manifestContent.trim()}
                      className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      Analyse Manifest
                    </button>
                  </form>
                )}

                {activeTab === 'image' && (
                  <form onSubmit={handleImageSubmit} className="space-y-4">
                    <div>
                      <label htmlFor="image" className="block text-sm font-medium text-slate-700 mb-1.5">
                        Docker image reference
                      </label>
                      <input
                        id="image"
                        type="text"
                        value={imageName}
                        onChange={e => setImageName(e.target.value)}
                        placeholder="nginx:1.29-alpine"
                        className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 font-mono text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        required
                      />
                      <p className="mt-1 text-xs text-slate-400">
                        Examples: <span className="font-mono">nginx:1.29-alpine</span> &nbsp;·&nbsp;
                        <span className="font-mono">python:3.12-slim</span> &nbsp;·&nbsp;
                        <span className="font-mono">node:22-alpine</span>
                      </p>
                      {isAuthenticated && (
                        <p className="mt-2 text-xs text-blue-600">
                          Signed in — full CVE scan via Trivy + SBOM report. Results saved to your dashboard.
                        </p>
                      )}
                    </div>
                    <button
                      type="submit"
                      disabled={!imageName.trim()}
                      className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      {isAuthenticated ? 'Start CVE Scan' : 'Fetch Image Metadata'}
                    </button>
                  </form>
                )}

                {error && (
                  <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                    {error}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="py-6 text-center text-xs text-slate-400">
        Docker & Kubernetes Analyzer &mdash; Phase 2
      </footer>
    </div>
  )
}
