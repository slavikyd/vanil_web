import React, { useState } from 'react'
import api from '../api'
import './LoginPage.css'

export default function LoginPage({ onLogin }) {
  const [cashierId, setCashierId] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await api.login(cashierId)
      
      if (!response.ok) {
        setError('Invalid cashier ID')
        setLoading(false)
        return
      }

      onLogin(cashierId, false)
      
    } catch (err) {
      setError('Login failed: ' + err.message)
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <h1>Order Management System</h1>
        <p className="subtitle">Cashier Login</p>

        {error && <div className="error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="cashier-id">Cashier ID</label>
            <input
              id="cashier-id"
              type="text"
              value={cashierId}
              onChange={(e) => setCashierId(e.target.value)}
              placeholder="Enter your cashier ID"
              required
              disabled={loading}
              autoFocus
            />
          </div>

          <button 
            type="submit" 
            className="btn-primary"
            disabled={loading || !cashierId}
          >
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  )
}
