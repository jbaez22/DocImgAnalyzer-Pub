import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import LoadingSpinner from './LoadingSpinner'
import type { ReactNode } from 'react'

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <LoadingSpinner message="Checking authentication..." />
  if (!user) return <Navigate to="/signin" state={{ from: location }} replace />
  return <>{children}</>
}
