const SERVER_URL = (import.meta.env.VITE_SERVER_URL || 'http://localhost:8787').replace(/\/$/, '')

function getToken() {
  return sessionStorage.getItem('token')
}

async function authFetch(path, opts = {}) {
  const token = getToken()
  const headers = { ...(opts.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${SERVER_URL}${path}`, { ...opts, headers })
  if (!res.ok) throw new Error(`${opts.method || 'GET'} ${path} failed: ${res.status}`)
  return res
}

export async function login(username, password) {
  const res = await fetch(`${SERVER_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `Login failed: ${res.status}`)
  }
  const data = await res.json()
  sessionStorage.setItem('token', data.access_token)
}

export async function getManifest() {
  const res = await authFetch('/manifest')
  return res.json()
}

export async function getImagesUrl() {
  const res = await authFetch('/images-url')
  const data = await res.json()
  return data.url
}

export async function getDataHash() {
  const res = await authFetch('/data-hash')
  const data = await res.json()
  return data.hash
}

export async function getImagesHash() {
  const res = await authFetch('/images-hash')
  const data = await res.json()
  return data.hash
}

export async function getObservations() {
  const res = await authFetch('/observations')
  return res.json()
}
