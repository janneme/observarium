import { writable, get } from 'svelte/store'

function persistedWritable(key, defaultValue) {
  let initial = defaultValue
  try {
    const raw = localStorage.getItem('observarium:' + key)
    if (raw !== null) initial = JSON.parse(raw)
  } catch {
    /* ignored */
  }
  const store = writable(initial)
  store.subscribe((v) => {
    try {
      localStorage.setItem('observarium:' + key, JSON.stringify(v))
    } catch {
      /* ignored */
    }
  })
  return store
}

export const showFovCircle = persistedWritable('showFovCircle', true)
export const FINDER_FOV_DEG = 7.5
export const fovCircleInstrument = persistedWritable('fovCircleInstrument', {
  mode: 'finder', // 'finder' | 'telescope'
  telescopeId: null,
  eyepieceId: null,
})
// Finder view's telescope-view instrument selection - independent of
// fovCircleInstrument above (see finder_view.md). No `mode` field: finder is
// always the implicit default, this only ever holds a telescope+eyepiece
// pair once the user has configured one.
export const finderInstrument = persistedWritable('finderInstrument', {
  telescopeId: null,
  eyepieceId: null,
})
export const showConstellationLines = persistedWritable('showConstellationLines', false)
export const showConstellationNames = persistedWritable('showConstellationNames', false)
export const showConstellationBoundaries = persistedWritable('showConstellationBoundaries', false)
export const showDsos = persistedWritable('showDsos', true)
export const showHorizon = persistedWritable('showHorizon', true)
export const showSolarSystem = persistedWritable('showSolarSystem', true)
export const solarSystemPositions = writable([]) // current computed positions, set by SkyCanvas
export const finderViewActive = writable(false)
export const searchViewActive = writable(false)
export const objectDetailsActive = writable(false)
export const pendingFocus = writable(null) // {ra, dec} — consumed by MainScreen to re-centre
export const pendingChanges = writable(0)

// Per-list local-only preferences, keyed by list id — deliberately kept out
// of the synced `getMeta('lists')` record (see lists.js) since this is a
// per-device display preference, not list content. A list with no entry here
// (new, or synced in from another device that hasn't set a local pref yet)
// defaults to highlightObserved: true.
export const listLocalPrefs = persistedWritable('listLocalPrefs', {})

export function getHighlightObserved(listId) {
  const prefs = get(listLocalPrefs)
  return prefs[listId]?.highlightObserved ?? true
}

export function setHighlightObserved(listId, value) {
  listLocalPrefs.update((prefs) => ({ ...prefs, [listId]: { ...prefs[listId], highlightObserved: value } }))
}

export function clearListLocalPrefs(listId) {
  listLocalPrefs.update((prefs) => {
    if (!(listId in prefs)) return prefs
    const next = { ...prefs }
    delete next[listId]
    return next
  })
}
