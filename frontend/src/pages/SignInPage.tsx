import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { confirmResetPassword, resetPassword, signIn } from 'aws-amplify/auth'
import { useAuth } from '../auth/useAuth'
import NavBar from '../components/NavBar'

type Step = 'signin' | 'forgot' | 'reset'

const EyeOff = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>
)

const EyeOn = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>
)

export default function SignInPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { refreshUser } = useAuth()
  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? '/dashboard'

  const [step, setStep] = useState<Step>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  function validatePassword(pw: string): string | null {
    if (pw.length < 12)            return 'Password must be at least 12 characters.'
    if (!/[A-Z]/.test(pw))         return 'Password must contain at least one uppercase letter.'
    if (!/[a-z]/.test(pw))         return 'Password must contain at least one lowercase letter.'
    if (!/[0-9]/.test(pw))         return 'Password must contain at least one number.'
    if (!/[^A-Za-z0-9]/.test(pw))  return 'Password must contain at least one special character (e.g. ! @ # $).'
    return null
  }

  async function handleSignIn(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await signIn({ username: email, password })
      await refreshUser()
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleForgot(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await resetPassword({ username: email })
    } catch {
      // Intentionally swallowed — never reveal whether the email is registered
    } finally {
      setLoading(false)
      setInfo(`If an account exists for ${email}, a reset code has been sent.`)
      setStep('reset')
    }
  }

  async function handleReset(e: FormEvent) {
    e.preventDefault()
    const pwError = validatePassword(newPassword)
    if (pwError) { setError(pwError); return }
    setLoading(true)
    setError(null)
    try {
      await confirmResetPassword({ username: email, confirmationCode: code, newPassword })
      setInfo('Password reset. You can now sign in.')
      setCode('')
      setNewPassword('')
      setStep('signin')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed.')
    } finally {
      setLoading(false)
    }
  }

  const titles: Record<Step, string> = {
    signin: 'Sign in',
    forgot: 'Reset password',
    reset: 'Set new password',
  }
  const subtitles: Record<Step, string> = {
    signin: 'Access your scan history and deep image analysis.',
    forgot: 'Enter your email and we\'ll send you a reset code.',
    reset: info ?? 'Enter the code from your email and choose a new password.',
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <NavBar />
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <h2 className="text-2xl font-bold text-slate-900 mb-1 text-center">{titles[step]}</h2>
          <p className="text-sm text-slate-500 text-center mb-8">{subtitles[step]}</p>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 space-y-5">

            {/* ── Step 1: Sign in ── */}
            {step === 'signin' && (
              <form onSubmit={handleSignIn} className="space-y-5">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-1.5">Email</label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                    required
                    autoFocus
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="password" className="block text-sm font-medium text-slate-700">Password</label>
                    <button
                      type="button"
                      onClick={() => { setError(null); setInfo(null); setStep('forgot') }}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Forgot password?
                    </button>
                  </div>
                  <div className="relative">
                    <input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 pr-10 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(v => !v)}
                      className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? <EyeOff /> : <EyeOn />}
                    </button>
                  </div>
                </div>

                {info && (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
                    {info}
                  </div>
                )}
                {error && (
                  <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? 'Signing in…' : 'Sign in'}
                </button>

                <p className="text-center text-sm text-slate-500">
                  No account?{' '}
                  <Link to="/signup" className="text-blue-600 hover:underline font-medium">Create one</Link>
                </p>
              </form>
            )}

            {/* ── Step 2: Request reset code ── */}
            {step === 'forgot' && (
              <form onSubmit={handleForgot} className="space-y-5">
                <div>
                  <label htmlFor="forgot-email" className="block text-sm font-medium text-slate-700 mb-1.5">Email</label>
                  <input
                    id="forgot-email"
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                    required
                    autoFocus
                  />
                </div>

                {error && (
                  <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? 'Sending…' : 'Send reset code'}
                </button>

                <p className="text-center text-sm text-slate-500">
                  <button type="button" onClick={() => { setError(null); setStep('signin') }} className="text-blue-600 hover:underline">
                    Back to sign in
                  </button>
                </p>
              </form>
            )}

            {/* ── Step 3: Submit code + new password ── */}
            {step === 'reset' && (
              <form onSubmit={handleReset} className="space-y-5">
                <div>
                  <label htmlFor="reset-code" className="block text-sm font-medium text-slate-700 mb-1.5">Reset code</label>
                  <input
                    id="reset-code"
                    type="text"
                    value={code}
                    onChange={e => setCode(e.target.value)}
                    placeholder="123456"
                    className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 tracking-widest text-center font-mono"
                    required
                    autoFocus
                  />
                </div>

                <div>
                  <label htmlFor="new-password" className="block text-sm font-medium text-slate-700 mb-1.5">New password</label>
                  <div className="relative">
                    <input
                      id="new-password"
                      type={showNewPassword ? 'text' : 'password'}
                      value={newPassword}
                      onChange={e => setNewPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 pr-10 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                      required
                      minLength={12}
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPassword(v => !v)}
                      className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600"
                      aria-label={showNewPassword ? 'Hide password' : 'Show password'}
                    >
                      {showNewPassword ? <EyeOff /> : <EyeOn />}
                    </button>
                  </div>
                  <p className="mt-1.5 text-xs text-slate-400">
                    12+ characters · uppercase · lowercase · number · special character
                  </p>
                </div>

                {error && (
                  <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? 'Resetting…' : 'Reset password'}
                </button>

                <p className="text-center text-sm text-slate-500">
                  <button type="button" onClick={() => { setError(null); setStep('forgot') }} className="text-blue-600 hover:underline">
                    Resend code
                  </button>
                </p>
              </form>
            )}

          </div>
        </div>
      </main>

      <footer className="py-6 text-center text-xs text-slate-400">
        Docker & Kubernetes Analyzer &mdash; Phase 3
      </footer>
    </div>
  )
}
