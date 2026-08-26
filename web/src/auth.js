const USER_KEY = 'sv_username'

export function getUsername() {
  return sessionStorage.getItem(USER_KEY) || ''
}

export function setAuth(username) {
  if (username) sessionStorage.setItem(USER_KEY, username)
}

export function clearAuth() {
  sessionStorage.removeItem(USER_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem('sv_token')
}
