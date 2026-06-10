import { writable } from 'svelte/store'

const DEFAULT = 'nightly'

function load() {
  try {
    const v = localStorage.getItem('observarium:theme')
    return v || DEFAULT
  } catch {
    return DEFAULT
  }
}

function persist(v) {
  try {
    localStorage.setItem('observarium:theme', v)
  } catch {
    // ignore
  }
}

export const theme = writable(load())

function applyTheme(v) {
  try {
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.setAttribute('data-theme', v)
    }
  } catch {
    // ignore (SSR or restricted env)
  }
  persist(v)
}

// Apply initial theme and persist changes
applyTheme(load())
theme.subscribe((v) => applyTheme(v))

export function toggleTheme() {
  theme.update((t) => (t === 'daily' ? 'nightly' : 'daily'))
}
