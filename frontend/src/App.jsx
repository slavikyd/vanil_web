import React, { useState, useEffect } from 'react'
import LoginPage from './pages/LoginPage'
import CashierPage from './pages/CashierPage'
import AdminPage from './pages/AdminPage'
import './App.css'

export default function App() {
  const [currentPage, setCurrentPage] = useState('login')
  const [cashierId, setCashierId] = useState(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [loading, setLoading] = useState(true)

  // Check if user is already logged in on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await fetch('/', {
          credentials: 'include',
        })
      } catch (error) {
        console.error('Auth check failed:', error)
      } finally {
        setLoading(false)
      }
    }

    checkAuth()
  }, [])

  const handleLogin = (id, isAdminUser) => {
    setCashierId(id)
    setIsAdmin(isAdminUser)
    setCurrentPage(isAdminUser ? 'admin' : 'cashier')
  }

  const handleLogout = () => {
    setCashierId(null)
    setIsAdmin(false)
    setCurrentPage('login')
  }

  if (loading) {
    return <div className="loading">Loading...</div>
  }

  return (
    <div className="app">
      {currentPage === 'login' && (
        <LoginPage onLogin={handleLogin} />
      )}
      {currentPage === 'cashier' && (
        <CashierPage 
          cashierId={cashierId} 
          onLogout={handleLogout}
          onAdminAccess={() => setCurrentPage('admin')}
          isAdmin={isAdmin}
        />
      )}
      {currentPage === 'admin' && (
        <AdminPage 
          cashierId={cashierId} 
          onLogout={handleLogout}
          onCashierView={() => setCurrentPage('cashier')}
        />
      )}
    </div>
  )
}
