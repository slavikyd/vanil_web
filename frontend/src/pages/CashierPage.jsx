import React, { useState, useEffect } from 'react'
import api from '../api'
import './CashierPage.css'

export default function CashierPage({ cashierId, onLogout, onAdminAccess, isAdmin: initialIsAdmin }) {
  const [items, setItems] = useState([])
  const [cart, setCart] = useState({})
  const [orderDate, setOrderDate] = useState(new Date().toISOString().split('T')[0])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [isAdmin, setIsAdmin] = useState(initialIsAdmin)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      setLoading(true)
      setError('')
      
      const response = await fetch('/api/data', {
        credentials: 'include',
      })
      
      if (!response.ok) {
        setError('Failed to load data')
        setItems([])
        setLoading(false)
        return
      }
      
      const data = await response.json()
      setItems(data.items || [])
      setIsAdmin(data.is_admin || false)
      setCart({})
      
    } catch (err) {
      setError('Failed to load data: ' + err.message)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  const handleAddToCart = async (itemId, quantity) => {
    try {
      setError('')
      
      // Optimistically update UI
      setCart(prev => ({
        ...prev,
        [itemId]: (prev[itemId] || 0) + quantity
      }))
      
      // Send to backend
      const tgId = document.querySelector('input[name="tg_id"]')?.value || cashierId
      await api.addToOrder(itemId, (cart[itemId] || 0) + quantity, tgId)
      
      setSuccess('Item added to cart')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError('Error adding to cart: ' + err.message)
    }
  }

  const handleQuantityChange = async (itemId, newQuantity) => {
    try {
      setError('')
      const qty = Math.max(0, newQuantity)
      
      setCart(prev => ({
        ...prev,
        [itemId]: qty
      }))
      
      const tgId = document.querySelector('input[name="tg_id"]')?.value || cashierId
      await api.addToOrder(itemId, qty, tgId)
      
    } catch (err) {
      setError('Error updating quantity: ' + err.message)
    }
  }

  const handleRemoveFromCart = (itemId) => {
    setCart(prev => {
      const newCart = { ...prev }
      delete newCart[itemId]
      return newCart
    })
  }

  const handlePlaceOrder = async (e) => {
  e.preventDefault()
  
  if (Object.keys(cart).length === 0) {
    setError('Cart is empty')
    return
  }

  try {
    setLoading(true)
    setError('')
    
    const tgId = document.querySelector('input[name="tg_id"]')?.value || cashierId
    
    // Ensure date is in YYYY-MM-DD format
    const dateStr = orderDate.split('T')[0]
    
    const response = await api.placeOrder(tgId, dateStr)
    
    if (!response.ok) {
      const text = await response.text()
      setError('Failed to place order: ' + text)
      setLoading(false)
      return
    }

    setSuccess('Order placed successfully!')
    setCart({})
    setTimeout(() => {
      setSuccess('')
      window.location.reload()
    }, 1500)
  } catch (err) {
    setError('Error placing order: ' + err.message)
  } finally {
    setLoading(false)
  }
}


  const cartTotal = Object.values(cart).reduce((sum, qty) => sum + qty, 0)

  return (
    <div className="page">
      <header className="header">
        <h1>Order Management</h1>
        <div className="header-actions">
          {isAdmin && (
            <button onClick={onAdminAccess} className="btn-admin">
              Admin Panel
            </button>
          )}
          <span>Cashier: {cashierId}</span>
          <button onClick={onLogout} className="btn-logout">
            Logout
          </button>
        </div>
      </header>

      <div className="container">
        {error && <div className="error">{error}</div>}
        {success && <div className="success">{success}</div>}

        {loading ? (
          <div className="loading">Loading...</div>
        ) : (
          <div className="cashier-layout">
            <div className="items-section">
              <h2>Available Items</h2>
              {items.length === 0 ? (
                <p>No items available</p>
              ) : (
                <div className="items-grid">
                  {items.map(item => (
                    <div key={item.id} className="item-card">
                      <h3>{item.name}</h3>
                      <p className="price">${item.price ? item.price.toFixed(2) : '0.00'}</p>
                      <div className="item-actions">
                        <button 
                          onClick={() => handleAddToCart(item.id, 1)}
                          className="btn-small"
                        >
                          Add to Cart
                        </button>
                        <span className="qty">
                          Qty: {cart[item.id] || 0}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="order-section">
              <h2>Place Order</h2>
              <form onSubmit={handlePlaceOrder}>
                <div className="form-group">
                  <label>Order Date</label>
                  <input 
                    type="date" 
                    value={orderDate}
                    onChange={(e) => setOrderDate(e.target.value)}
                    required
                  />
                </div>

                <div className="cart-summary">
                  <h3>Cart Summary</h3>
                  {Object.keys(cart).length === 0 ? (
                    <p>Cart is empty</p>
                  ) : (
                    <>
                      <div className="cart-items">
                        {Object.entries(cart).map(([itemId, qty]) => {
                          const item = items.find(i => i.id === itemId)
                          return (
                            <div key={itemId} className="cart-item">
                              <div>
                                <span>{item?.name || `Item ${itemId}`}</span>
                                <div style={{ display: 'flex', gap: '5px', marginTop: '5px' }}>
                                  <button
                                    type="button"
                                    onClick={() => handleQuantityChange(itemId, qty - 1)}
                                    style={{ padding: '4px 8px', cursor: 'pointer' }}
                                  >
                                    −
                                  </button>
                                  <input 
                                    type="number" 
                                    value={qty}
                                    onChange={(e) => handleQuantityChange(itemId, parseInt(e.target.value) || 0)}
                                    style={{ width: '50px', textAlign: 'center' }}
                                    min="0"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => handleQuantityChange(itemId, qty + 1)}
                                    style={{ padding: '4px 8px', cursor: 'pointer' }}
                                  >
                                    +
                                  </button>
                                </div>
                              </div>
                              <button
                                type="button"
                                onClick={() => handleRemoveFromCart(itemId)}
                                style={{ marginLeft: '10px', padding: '4px 8px', background: '#ff6b6b', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                              >
                                Remove
                              </button>
                            </div>
                          )
                        })}
                      </div>
                      <div className="cart-total">
                        Total Items: {cartTotal}
                      </div>
                    </>
                  )}
                </div>

                <button 
                  type="submit" 
                  className="btn-primary"
                  disabled={loading || Object.keys(cart).length === 0}
                >
                  {loading ? 'Placing Order...' : 'Place Order'}
                </button>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
