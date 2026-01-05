/**
 * API client for communicating with FastAPI backend
 * Handles authentication with session cookies (no JWT needed)
 */

const API_BASE = ''  // Proxy handled by vite.config.js

export const api = {
  // Auth endpoints
  login: async (cashierId) => {
    const formData = new FormData()
    formData.append('cashier_id', cashierId)
    
    const response = await fetch('/login', {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    return response
  },

  logout: async () => {
    const response = await fetch('/logout', {
      method: 'POST',
      credentials: 'include',
    })
    return response
  },

  // Orders CRUD
  addToOrder: async (itemId, quantity, tgId) => {
    const response = await fetch('/add-to-order', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        item_id: itemId,
        quantity: quantity,
        tg_id: tgId,
      }),
      credentials: 'include',
    })
    return response.json()
  },

  placeOrder: async (tgId, orderFor) => {
    const formData = new FormData()
    formData.append('tg_id', tgId)
    formData.append('order_for', orderFor)
    
    const response = await fetch('/place_order', {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    return response
  },

  getOrders: async () => {
    const response = await fetch('/orders', {
      credentials: 'include',
    })
    return response.json()
  },

  // Admin endpoints
  createItem: async (name, price, ttl) => {
    const formData = new FormData()
    formData.append('name', name)
    formData.append('price', price)
    formData.append('ttl', ttl)
    
    const response = await fetch('/admin/items/create', {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    return response
  },

  getAdminItems: async () => {
    const response = await fetch('/admin/items', {
      credentials: 'include',
    })
    return response.json()
  },

  deleteItem: async (itemId) => {
    const formData = new FormData()
    formData.append('item_id', itemId)
    
    const response = await fetch('/admin/items/delete', {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    return response
  },

  toggleItemActivity: async (itemId, isActive) => {
    const formData = new FormData()
    formData.append('item_id', itemId)
    formData.append('is_active', isActive)
    
    const response = await fetch('/admin/items/toggle', {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    return response
  },

  getAdminOrders: async (orderForDate, address) => {
    const params = new URLSearchParams()
    if (orderForDate) params.append('order_for_date', orderForDate)
    if (address) params.append('address', address)
    
    const response = await fetch(`/admin/orders?${params}`, {
      credentials: 'include',
    })
    return response.json()
  },

  deleteOrder: async (orderId) => {
    const formData = new FormData()
    formData.append('order_id', orderId)
    
    const response = await fetch('/admin/orders/delete', {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    return response
  },

  exportOrders: async (address) => {
    const params = new URLSearchParams()
    if (address) params.append('address', address)
    
    const response = await fetch(`/admin/orders/export?${params}`, {
      credentials: 'include',
    })
    return response.blob()
  },

  exportByAddress: async (orderFor) => {
    const response = await fetch(`/admin/export/by_address?order_for=${orderFor}`, {
      credentials: 'include',
    })
    return response.blob()
  },

  exportAllItems: async (orderFor) => {
    const response = await fetch(`/admin/export/all_items?order_for=${orderFor}`, {
      credentials: 'include',
    })
    return response.blob()
  },
}

export default api
