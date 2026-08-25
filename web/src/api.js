const API_BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options = {}) {
  const token = localStorage.getItem('sv_token')
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 100000)
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: controller.signal })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(body.detail || body.message || `请求失败 (${res.status})`)
    if (body.code !== 0) throw new Error(body.message || '请求失败')
    return body.data
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('请求超时，请稍后重试')
    throw e
  } finally {
    clearTimeout(timer)
  }
}

export const getCities = () => request('/api/cities')
export const getAgents = () => request('/api/agents')
export const sendChat = (message, sessionId) =>
  request('/api/chat', { method: 'POST', body: JSON.stringify({ message, session_id: sessionId }) })
export const queryWeather = (message) =>
  request('/api/weather', { method: 'POST', body: JSON.stringify({ message }) })
export const queryTicket = (message) =>
  request('/api/ticket', { method: 'POST', body: JSON.stringify({ message }) })
export const queryTicketOrder = (message) =>
  request('/api/ticket-order', { method: 'POST', body: JSON.stringify({ message }) })
export const queryHotel = (message) =>
  request('/api/hotel', { method: 'POST', body: JSON.stringify({ message }) })
export const queryItinerary = (message) =>
  request('/api/itinerary', { method: 'POST', body: JSON.stringify({ message }) })
export const login = (username, password) =>
  request('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) })
export const register = (payload) =>
  request('/api/register', { method: 'POST', body: JSON.stringify(payload) })
export const getOrders = () => request('/api/orders')
export const cancelOrder = (orderNo) =>
  request('/api/orders/cancel', { method: 'POST', body: JSON.stringify({ order_no: orderNo }) })
