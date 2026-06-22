import { writable } from 'svelte/store'

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
