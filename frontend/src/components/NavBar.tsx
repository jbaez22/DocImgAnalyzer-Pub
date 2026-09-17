import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'

export default function NavBar() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  async function handleSignOut() {
    await signOut()
    navigate('/')
  }

  return (
    <header className="bg-white border-b border-slate-200">
      <div className="mx-auto max-w-4xl px-4 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="h-8 w-8 rounded-lg bg-blue-600 flex items-center justify-center">
            <span className="text-white text-sm font-bold">D</span>
          </div>
          <div>
            <p className="text-sm font-bold text-slate-900 group-hover:text-blue-700 transition-colors">
              Docker & Kubernetes Analyzer
            </p>
            <p className="text-xs text-slate-500">Security &amp; best-practice</p>
          </div>
        </Link>

        <nav className="flex items-center gap-4">
          {user ? (
            <>
              <Link
                to="/dashboard"
                className="text-sm font-medium text-slate-600 hover:text-blue-700 transition-colors"
              >
                Dashboard
              </Link>
              <Link
                to="/billing"
                className="text-sm font-medium text-slate-600 hover:text-blue-700 transition-colors"
              >
                Billing
              </Link>
              <Link
                to="/keys"
                className="text-sm font-medium text-slate-600 hover:text-blue-700 transition-colors hidden sm:block"
              >
                API Keys
              </Link>
              <span className="text-xs text-slate-400 hidden lg:block">{user.email}</span>
              <button
                onClick={handleSignOut}
                className="text-sm font-medium text-slate-500 hover:text-red-600 transition-colors"
              >
                Sign out
              </button>
            </>
          ) : (
            <Link
              to="/signin"
              className="text-sm font-semibold text-blue-600 hover:text-blue-700 transition-colors"
            >
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  )
}
