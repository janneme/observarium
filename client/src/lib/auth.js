export function getTokenStatus() {
  const token = sessionStorage.getItem('token')
  if (!token) return { valid: false, nearExpiry: false }
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return { valid: false, nearExpiry: false }
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
    const exp = payload.exp
    if (!exp) return { valid: true, nearExpiry: false }
    const now = Date.now() / 1000
    if (exp <= now) return { valid: false, nearExpiry: false }
    const nearExpiry = exp - now < 300
    return { valid: true, nearExpiry }
  } catch {
    return { valid: false, nearExpiry: false }
  }
}
