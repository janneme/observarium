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
// {ra, dec, fov?} — consumed by MainScreen to re-centre (and, when fov is
// given, re-zoom) the sky view. fov is optional so existing pan-only callers
// (FinderPanel's search, SearchPanel) are unaffected.
export const pendingFocus = writable(null)
export const pendingChanges = writable(0)

// "Return to where I came from" for the object-actions tooltip (Lists/
// Observations/Observed Objects/Finding Paths target) and the pre-existing
// About/Finder navigation they now share a mechanism with. Each destination
// gets its own independent slot rather than one shared store, because
// e.g. opening About *from* Finder clears/sets state in the same tick as
// leaving Finder - sharing one slot between "return after Finder closes" and
// "return after About closes" would collide right at that transition.
//
// Origin values: 'lists' | 'observations' | 'observedObjects' |
// 'findingPaths' | 'findingPathsList' | 'finder' (the last only valid for
// aboutReturnOrigin, matching the pre-existing Finder->About flow). Always
// exactly one level deep, same as the boolean flags this replaces.
export const aboutReturnOrigin = writable(null) // string | null
export const finderReturnOrigin = writable(null) // string | null
// {screen, objectId} | null - objectId is snapshotted so MainScreen can tell
// "the user is still looking at the object they navigated to" (pan/zoom/swipe
// don't change it) apart from "the user selected something else" (does).
export const skyViewReturnOrigin = writable(null)

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

// "Sky pollution" slider, 0 (dark sky, no reduction) – 100 (big-city glow).
// Local device setting only — never synced to the server, deliberately
// separate from any per-list/instrument preference above. Modelled as a
// straight magnitude *reduction* (delta), not an absolute cap: light
// pollution washes out the naked-eye limit from a pristine ~6.5 down to ~2.5
// (a 4.0-mag loss at full pollution), and that same delta is subtracted from
// whatever theoretical limit each view (sky view, finder/telescope view,
// Visual Range planner) would otherwise use. A delta - rather than an
// absolute cap like "everything becomes mag 2.5" - is what makes the effect
// visible immediately across the whole slider: an absolute cap only bites
// once it drops below a view's own current limit, which for the wide-FOV
// sky view (natural limit ~5) left most of the slider range with no visible
// effect at all.
const NAKED_EYE_MIN_MAG = 6.5 // pollution=0: pristine dark-sky naked-eye limit
const NAKED_EYE_MAX_MAG = 2.5 // pollution=100: big-city naked-eye limit

// Same generic FOV→limiting-magnitude formula as SkyCanvas/FinderPanel/
// MainScreen (each keeps its own local copy - see comments there) - used
// here only to compute the finder view's theoretical limit for the default
// below, not for any actual rendering decision.
const _FOV_MAG5 = 120
const _FOV_MAG14 = 2
function _adaptiveMagLimit(fovDeg) {
  return Math.min(14, Math.max(5, 5 + (9 * Math.log2(_FOV_MAG5 / fovDeg)) / Math.log2(_FOV_MAG5 / _FOV_MAG14)))
}

// Default chosen so the finder view (whose own theoretical limit is ~11.1)
// renders down to exactly mag 9 out of the box.
const SKY_POLLUTION_DEFAULT_TARGET_MAG = 9
export const DEFAULT_SKY_POLLUTION =
  ((_adaptiveMagLimit(FINDER_FOV_DEG) - SKY_POLLUTION_DEFAULT_TARGET_MAG) / (NAKED_EYE_MIN_MAG - NAKED_EYE_MAX_MAG)) *
  100

export const skyPollution = persistedWritable('skyPollution', DEFAULT_SKY_POLLUTION)

// Naked-eye limiting magnitude at this pollution level — used both for the
// slider's readout and as the basis for skyPollutionDelta() below. Always a
// plain number across the whole 0-100 range.
export function nakedEyeLimitDisplay(pollution) {
  const p = Math.max(0, Math.min(100, pollution))
  return NAKED_EYE_MIN_MAG + (NAKED_EYE_MAX_MAG - NAKED_EYE_MIN_MAG) * (p / 100)
}

// Magnitude reduction to subtract from any view's own theoretical/adaptive
// limit: 0 at pollution=0 (so "minimum → theoretical visual range applies"
// holds exactly, no clamping at all), rising to 4.0 at pollution=100.
export function skyPollutionDelta(pollution) {
  return NAKED_EYE_MIN_MAG - nakedEyeLimitDisplay(pollution)
}

// Convenience: theoreticalLimit reduced by the current pollution delta.
export function applySkyPollution(theoreticalLimit, pollution) {
  return theoreticalLimit - skyPollutionDelta(pollution)
}

// Observed Objects screen — sort choice, filter form fields, and whether the
// sky-view hide filter is currently applied. Local device setting only, same
// persistedWritable pattern as skyPollution/listLocalPrefs above — never
// synced to the server (see observed_objects.md).
export const observedObjectsState = persistedWritable('observedObjectsState', {
  sort: 'name', // 'name' | 'newest' | 'oldest' | 'easy' | 'hard' | 'count'
  filter: {
    telescopeId: null,
    year: null,
    minObs: null,
    maxObs: null,
    name: '',
    objectType: null,
  },
  hideActive: false,
})
