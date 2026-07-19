const DEFAULT_SERVER_URL = (import.meta.env.VITE_SERVER_URL || 'http://localhost:8787').replace(/\/$/, '')
export const CLOUD_SERVER_URL = (import.meta.env.VITE_CLOUD_SERVER_URL || '').replace(/\/$/, '')

// Runtime-selectable backend — lets the (dev-only) sync setup screen switch
// between the local dev server and the deployed cloud Lambda without a
// rebuild. Every request below reads this at call time rather than closing
// over a module-load-time constant.
let _activeServerUrl = DEFAULT_SERVER_URL

export function setActiveServerUrl(url) {
  _activeServerUrl = (url || DEFAULT_SERVER_URL).replace(/\/$/, '')
}

export function getActiveServerUrl() {
  return _activeServerUrl
}

function getToken() {
  return sessionStorage.getItem('token')
}

async function authFetch(path, opts = {}) {
  const token = getToken()
  const headers = { ...(opts.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${_activeServerUrl}${path}`, { ...opts, headers })
  if (!res.ok) {
    const err = new Error(`${opts.method || 'GET'} ${path} failed: ${res.status}`)
    if (res.status === 401) err.authExpired = true
    throw err
  }
  return res
}

async function authFetchJson(path, body) {
  const res = await authFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function login(username, password) {
  const res = await fetch(`${_activeServerUrl}/login`, {
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

export async function getManifest(mag) {
  const path = mag != null ? `/manifest?mag=${mag}` : '/manifest'
  const res = await authFetch(path)
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

export async function saveObservations(observations) {
  return authFetchJson('/observations', observations)
}

export async function mergeObservations(upserts, deletes) {
  return authFetchJson('/observations/merge', { upserts, deletes })
}

export async function getFindingPaths() {
  const res = await authFetch('/finding-paths')
  return res.json()
}

export async function saveFindingPaths(data) {
  return authFetchJson('/finding-paths', data)
}

export async function mergeFindingPaths(upserts, deletes) {
  return authFetchJson('/finding-paths/merge', { upserts, deletes })
}

export async function getTelescopes() {
  const res = await authFetch('/telescopes')
  return res.json()
}

export async function saveTelescopes(items) {
  return authFetchJson('/telescopes', items)
}

export async function mergeTelescopes(upserts, deletes) {
  return authFetchJson('/telescopes/merge', { upserts, deletes })
}

export async function getEyepieces() {
  const res = await authFetch('/eyepieces')
  return res.json()
}

export async function saveEyepieces(items) {
  return authFetchJson('/eyepieces', items)
}

export async function mergeEyepieces(upserts, deletes) {
  return authFetchJson('/eyepieces/merge', { upserts, deletes })
}
