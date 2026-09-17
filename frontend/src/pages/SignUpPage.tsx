import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { confirmSignUp, signIn, signUp } from 'aws-amplify/auth'
import { useAuth } from '../auth/useAuth'
import NavBar from '../components/NavBar'

type Step = 'register' | 'confirm'

export default function SignUpPage() {
  const navigate = useNavigate()
  const { refreshUser } = useAuth()

  const [step, setStep] = useState<Step>('register')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  function validatePassword(pw: string): string | null {
    if (pw.length < 12)          return 'Password must be at least 12 characters.'
    if (!/[A-Z]/.test(pw))       return 'Password must contain at least one uppercase letter.'
    if (!/[a-z]/.test(pw))       return 'Password must contain at least one lowercase letter.'
    if (!/[0-9]/.test(pw))       return 'Password must contain at least one number.'
    if (!/[^A-Za-z0-9]/.test(pw)) return 'Password must contain at least one special character (e.g. ! @ # $).'
    return null
  }

  async function handleRegister(e: FormEvent) {
    e.preventDefault()
    const pwError = validatePassword(password)
    if (pwError) { setError(pwError); return }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      await signUp({ username: email, password, options: { userAttributes: { email } } })
      setStep('confirm')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed.')
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await confirmSignUp({ username: email, confirmationCode: code })
      await signIn({ username: email, password })
      await refreshUser()
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Confirmation failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <NavBar />
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <h2 className="text-2xl font-bold text-slate-900 mb-1 text-center">
            {step === 'register' ? 'Create account' : 'Verify your email'}
          </h2>
          <p className="text-sm text-slate-500 text-center mb-8">
            {step === 'register'
              ? 'Get access to deep CVE scanning and scan history.'
              : `We sent a verification code to ${email}.`}
          </p>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 space-y-5">
            {step === 'register' ? (
              <form onSubmit={handleRegister} className="space-y-5">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-1.5">
                    Email
                  </label>
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
                  <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1.5">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 pr-10 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                      required
                      minLength={12}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(v => !v)}
                      className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                          <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                          <line x1="1" y1="1" x2="23" y2="23"/>
                        </svg>
                      ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                          <circle cx="12" cy="12" r="3"/>
                        </svg>
                      )}
                    </button>
                  </div>
                  <p className="mt-1.5 text-xs text-slate-400">
                    12+ characters · uppercase · lowercase · number · special character
                  </p>
                </div>

                <div>
                  <label htmlFor="confirm" className="block text-sm font-medium text-slate-700 mb-1.5">
                    Confirm password
                  </label>
                  <div className="relative">
                    <input
                      id="confirm"
                      type={showConfirm ? 'text' : 'password'}
                      value={confirm}
                      onChange={e => setConfirm(e.target.value)}
                      placeholder="••••••••"
                      className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 pr-10 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirm(v => !v)}
                      className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600"
                      aria-label={showConfirm ? 'Hide password' : 'Show password'}
                    >
                      {showConfirm ? (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                          <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                          <line x1="1" y1="1" x2="23" y2="23"/>
                        </svg>
                      ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                          <circle cx="12" cy="12" r="3"/>
                        </svg>
                      )}
                    </button>
                  </div>
                </div>

                {error && (
                  <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? 'Creating account…' : 'Create account'}
                </button>

                <p className="text-center text-sm text-slate-500">
                  Already have an account?{' '}
                  <Link to="/signin" className="text-blue-600 hover:underline font-medium">
                    Sign in
                  </Link>
                </p>
              </form>
            ) : (
              <form onSubmit={handleConfirm} className="space-y-5">
                <div>
                  <label htmlFor="code" className="block text-sm font-medium text-slate-700 mb-1.5">
                    Verification code
                  </label>
                  <input
                    id="code"
                    type="text"
                    value={code}
                    onChange={e => setCode(e.target.value)}
                    placeholder="123456"
                    className="w-full rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 tracking-widest text-center font-mono"
                    required
                    autoFocus
                  />
                </div>

                {error && (
                  <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {loading ? 'Verifying…' : 'Verify and sign in'}
                </button>
              </form>
            )}
          </div>
        </div>
      </main>

      <footer className="py-6 text-center text-xs text-slate-400">
        Docker & Kubernetes Analyzer &mdash; Phase 2
      </footer>
    </div>
  )
}
