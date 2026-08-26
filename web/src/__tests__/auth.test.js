import { beforeEach, describe, expect, it } from 'vitest'
import { clearAuth, getUsername, setAuth } from '../auth.js'

describe('auth storage', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it('stores username in sessionStorage only', () => {
    setAuth('tester')
    expect(sessionStorage.getItem('sv_username')).toBe('tester')
    expect(sessionStorage.getItem('sv_token')).toBeNull()
    expect(getUsername()).toBe('tester')
  })

  it('clearAuth removes both storages', () => {
    localStorage.setItem('sv_token', 'legacy-token')
    setAuth('tester')
    clearAuth()
    expect(getUsername()).toBe('')
    expect(sessionStorage.getItem('sv_token')).toBeNull()
    expect(localStorage.getItem('sv_token')).toBeNull()
  })
})
