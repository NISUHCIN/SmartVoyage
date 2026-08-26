const TOKEN_KEY = 'sv_token'
const USER_KEY = 'sv_username'

export function getToken() {
  let token = sessionStorage.getItem(TOKEN_KEY)
  if (!token && localStorage.getItem(TOKEN_KEY)) {
    token = localStorage.getItem(TOKEN_KEY)
    sessionStorage.setItem(TOKEN_KEY, token)
    const username = localStorage.getItem(USER_KEY)
    if (username) sessionStorage.setItem(USER_KEY, username)
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }
  return token
}

export function getUsername() {
  return sessionStorage.getItem(USER_KEY) || localStorage.getItem(USER_KEY) || ''
}

export function setAuth(token, username) {
  if (username) sessionStorage.setItem(USER_KEY, username)
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function clearAuth() {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
