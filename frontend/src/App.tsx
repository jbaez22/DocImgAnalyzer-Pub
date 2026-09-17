import './auth/amplify'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import HomePage from './pages/HomePage'
import ResultsPage from './pages/ResultsPage'
import SignInPage from './pages/SignInPage'
import SignUpPage from './pages/SignUpPage'
import DashboardPage from './pages/DashboardPage'
import DeepResultsPage from './pages/DeepResultsPage'
import BillingPage from './pages/BillingPage'
import ApiKeysPage from './pages/ApiKeysPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* v1 — public */}
          <Route path="/" element={<HomePage />} />
          <Route path="/results/:scanId" element={<ResultsPage />} />

          {/* auth */}
          <Route path="/signin" element={<SignInPage />} />
          <Route path="/signup" element={<SignUpPage />} />

          {/* v2 — protected */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/v2/results/:scanId"
            element={
              <ProtectedRoute>
                <DeepResultsPage />
              </ProtectedRoute>
            }
          />

          {/* v3 — protected */}
          <Route
            path="/billing"
            element={
              <ProtectedRoute>
                <BillingPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/keys"
            element={
              <ProtectedRoute>
                <ApiKeysPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
