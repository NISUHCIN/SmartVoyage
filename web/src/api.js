const API_BASE = import.meta.env.VITE_API_BASE || ''

function makeRequestId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'req-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10)
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', 'X-Request-ID': makeRequestId(), ...(options.headers || {}) }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 100000)
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include', signal: controller.signal })
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
export async function sendChatStream(message, sessionId, onDelta) {
  const headers = { 'Content-Type': 'application/json', 'X-Request-ID': makeRequestId() }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 120000)
  try {
    const res = await fetch(`${API_BASE}/api/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ message, session_id: sessionId }),
      credentials: 'include',
      signal: controller.signal
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || body.message || `请求失败 (${res.status})`)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let returnedSessionId = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let sep
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        const line = raw.split('\n').find((l) => l.startsWith('data: '))
        if (!line) continue
        const payload = JSON.parse(line.slice(6))
        if (payload.session_id) returnedSessionId = payload.session_id
        if (payload.delta) onDelta(payload.delta)
      }
    }
    return { session_id: returnedSessionId }
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('请求超时，请稍后重试')
    throw e
  } finally {
    clearTimeout(timer)
  }
}
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
export const getSessions = () => request('/api/sessions')
export const createSession = (title = '新对话') =>
  request('/api/sessions', { method: 'POST', body: JSON.stringify({ title }) })
export const getMessages = (sessionId) => request(`/api/messages/${sessionId}`)
export const getMe = () => request('/api/me')
export const logout = () => request('/api/logout', { method: 'POST' })
