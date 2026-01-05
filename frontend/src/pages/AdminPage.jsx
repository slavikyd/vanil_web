import React, { useState, useEffect } from 'react'
import api from '../api'
import './AdminPage.css'

export default function AdminPage({ cashierId, onLogout, onCashierView }) {
  const [currentTab, setCurrentTab] = useState('items')
  const [items, setItems] = useState([])
  const [orders, setOrders] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  
  const [itemName, setItemName] = useState('')
  const [itemPrice, setItemPrice] = useState('')
  const [itemTtl, setItemTtl] = useState('')
  const [filterDate, setFilterDate] = useState('')
  const [filterAddress, setFilterAddress] = useState('')
  const [itemCheckboxes, setItemCheckboxes] = useState({})

  useEffect(() => {
    if (currentTab === 'items') {
      fetchItems()
    } else {
      fetchOrders()
    }
  }, [currentTab])

  const fetchItems = async () => {
    try {
      setLoading(true)
      setError('')
      
      const response = await fetch('/admin/items', {
        credentials: 'include',
      })
      
      if (!response.ok) {
        setError('Failed to load items')
        setItems([])
        return
      }
      
      const html = await response.text()
      
      // Parse items from HTML table
      const itemRows = html.match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || []
      const parsedItems = []
      const checkboxStates = {}
      
      itemRows.forEach((row, idx) => {
        if (idx === 0) return // Skip header
        
        const nameMatch = row.match(/<td>([^<]+)<\/td>/)
        const checkedMatch = row.match(/checked/) ? true : false
        const idMatch = row.match(/value="([^"]+)"/)
        
        if (nameMatch && idMatch) {
          const itemId = idMatch[1]
          parsedItems.push({
            id: itemId,
            name: nameMatch[1].trim(),
            active: checkedMatch
          })
          checkboxStates[itemId] = checkedMatch
        }
      })
      
      setItems(parsedItems)
      setItemCheckboxes(checkboxStates)
    } catch (err) {
      setError('Failed to load items: ' + err.message)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  const fetchOrders = async () => {
    try {
      setLoading(true)
      setError('')
      
      const params = new URLSearchParams()
      if (filterDate) params.append('order_for_date', filterDate)
      if (filterAddress) params.append('address', filterAddress)
      
      const response = await fetch(`/admin/orders?${params}`, {
        credentials: 'include',
      })
      
      if (!response.ok) {
        setError('Failed to load orders')
        setOrders({})
        return
      }
      
      const html = await response.text()
      setOrders({})
      
    } catch (err) {
      setError('Failed to load orders: ' + err.message)
      setOrders({})
    } finally {
      setLoading(false)
    }
  }

  const handleCreateItem = async (e) => {
    e.preventDefault()
    
    if (!itemName || !itemPrice || !itemTtl) {
      setError('All fields are required')
      return
    }

    try {
      setLoading(true)
      setError('')
      
      const response = await api.createItem(itemName, parseFloat(itemPrice), parseInt(itemTtl))
      
      if (!response.ok) {
        setError('Failed to create item')
        return
      }

      setSuccess('Item created successfully!')
      setItemName('')
      setItemPrice('')
      setItemTtl('')
      fetchItems()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError('Error creating item: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleToggleItem = async (itemId) => {
    try {
      setError('')
      
      // Send to backend with FormData (like the template does)
      const formData = new FormData()
      
      // Add all items to the form
      items.forEach(item => {
        // If this is the item being toggled, send opposite state
        // Otherwise, send current state
        if (item.id === itemId) {
          if (!itemCheckboxes[item.id]) {
            formData.append(`active_${item.id}`, 'true')
          }
        } else {
          if (itemCheckboxes[item.id]) {
            formData.append(`active_${item.id}`, 'true')
          }
        }
      })
      
      const response = await fetch('/admin/items/toggle', {
        method: 'POST',
        body: formData,
        credentials: 'include',
      })
      
      if (!response.ok) {
        setError('Failed to toggle item')
        return
      }

      // Update local state
      setItemCheckboxes(prev => ({
        ...prev,
        [itemId]: !prev[itemId]
      }))

      setSuccess('Item updated successfully!')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError('Error toggling item: ' + err.message)
    }
  }

  const handleDeleteItem = async (itemId) => {
    if (!window.confirm('Are you sure you want to delete this item?')) return

    try {
      setLoading(true)
      setError('')
      
      const response = await api.deleteItem(itemId)
      
      if (!response.ok) {
        setError('Failed to delete item')
        return
      }

      setSuccess('Item deleted successfully!')
      fetchItems()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError('Error deleting item: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteOrder = async (orderId) => {
    if (!window.confirm('Are you sure you want to delete this order?')) return

    try {
      setLoading(true)
      setError('')
      
      const response = await api.deleteOrder(orderId)
      
      if (!response.ok) {
        setError('Failed to delete order')
        return
      }

      setSuccess('Order deleted successfully!')
      fetchOrders()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError('Error deleting order: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async (type) => {
    try {
      setLoading(true)
      setError('')
      
      let blob
      if (type === 'orders') {
        blob = await api.exportOrders(filterAddress)
      } else if (type === 'byAddress') {
        if (!filterDate) {
          setError('Please select a date')
          return
        }
        blob = await api.exportByAddress(filterDate)
      } else if (type === 'allItems') {
        if (!filterDate) {
          setError('Please select a date')
          return
        }
        blob = await api.exportAllItems(filterDate)
      }

      // Download file
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `export_${Date.now()}.xlsx`
      a.click()
      window.URL.revokeObjectURL(url)

      setSuccess('File exported successfully!')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err) {
      setError('Error exporting: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Admin Panel</h1>
        <div className="header-actions">
          <button onClick={onCashierView} className="btn-cashier">
            Cashier View
          </button>
          <span>Admin: {cashierId}</span>
          <button onClick={onLogout} className="btn-logout">
            Logout
          </button>
        </div>
      </header>

      <div className="container">
        {error && <div className="error">{error}</div>}
        {success && <div className="success">{success}</div>}

        <div className="admin-tabs">
          <button 
            className={`tab ${currentTab === 'items' ? 'active' : ''}`}
            onClick={() => setCurrentTab('items')}
          >
            Manage Items
          </button>
          <button 
            className={`tab ${currentTab === 'orders' ? 'active' : ''}`}
            onClick={() => setCurrentTab('orders')}
          >
            Manage Orders
          </button>
        </div>

        {loading && <div className="loading">Loading...</div>}

        {currentTab === 'items' && (
          <div className="admin-section">
            <h2>Create New Item</h2>
            <form onSubmit={handleCreateItem} className="admin-form">
              <div className="form-row">
                <div className="form-group">
                  <label>Item Name</label>
                  <input 
                    type="text" 
                    value={itemName}
                    onChange={(e) => setItemName(e.target.value)}
                    placeholder="Enter item name"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Price</label>
                  <input 
                    type="number" 
                    step="0.01"
                    value={itemPrice}
                    onChange={(e) => setItemPrice(e.target.value)}
                    placeholder="Enter price"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>TTL (Days)</label>
                  <input 
                    type="number" 
                    value={itemTtl}
                    onChange={(e) => setItemTtl(e.target.value)}
                    placeholder="Enter TTL"
                    required
                  />
                </div>
                <button type="submit" className="btn-primary" disabled={loading}>
                  {loading ? 'Creating...' : 'Create Item'}
                </button>
              </div>
            </form>

            <h2 style={{ marginTop: '40px' }}>Existing Items</h2>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Active</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.length === 0 ? (
                    <tr>
                      <td colSpan="3" style={{ textAlign: 'center' }}>No items found</td>
                    </tr>
                  ) : (
                    items.map(item => (
                      <tr key={item.id}>
                        <td>{item.name}</td>
                        <td>
                          <input 
                            type="checkbox" 
                            checked={itemCheckboxes[item.id] || false}
                            onChange={() => handleToggleItem(item.id)}
                            style={{ cursor: 'pointer' }}
                          />
                        </td>
                        <td>
                          <button 
                            onClick={() => handleDeleteItem(item.id)}
                            className="btn-delete"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {currentTab === 'orders' && (
          <div className="admin-section">
            <h2>Filter Orders</h2>
            <div className="filter-form">
              <div className="form-group">
                <label>Filter by Date</label>
                <input 
                  type="date" 
                  value={filterDate}
                  onChange={(e) => setFilterDate(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Filter by Address</label>
                <input 
                  type="text" 
                  value={filterAddress}
                  onChange={(e) => setFilterAddress(e.target.value)}
                  placeholder="Search address"
                />
              </div>
              <div className="export-buttons">
                <button 
                  onClick={() => handleExport('orders')}
                  className="btn-export"
                  disabled={loading}
                >
                  Export All
                </button>
                <button 
                  onClick={() => handleExport('byAddress')}
                  className="btn-export"
                  disabled={loading || !filterDate}
                >
                  Export by Address
                </button>
                <button 
                  onClick={() => handleExport('allItems')}
                  className="btn-export"
                  disabled={loading || !filterDate}
                >
                  Export All Items
                </button>
              </div>
            </div>

            <h2 style={{ marginTop: '40px' }}>Orders</h2>
            <p>Orders will be loaded from the backend</p>
          </div>
        )}
      </div>
    </div>
  )
}
