// Schematic Moon map math: projecting named surface features (from
// moon_features.json) onto the apparent lunar disc, and modeling a
// simplified terminator/illumination for the Moon Quiz. See
// IMPLEMENTATION_STEPS.md Step 40 for the design rationale — this is
// deliberately a labeled schematic diagram (position + approximate size),
// not a photorealistic render: the source data has no elevation/relief and
// no true boundary polygons, only per-feature center + size/bounding-box.
import { Libration, MoonPhase } from 'astronomy-engine'

const D2R = Math.PI / 180

// A feature closer to the limb than this (cosine of angular distance from
// the sub-Earth point) is excluded from quiz pools — too foreshortened/
// edge-on to be a fair question regardless of difficulty.
export const LIMB_COS_CUTOFF = 0.15

// "Near terminator" window for Local scope (medium/hard): lit side only
// (illumCos > 0), within this distance of the terminator (illumCos == 0).
export const TERMINATOR_ABS_COS = 0.3

// Apparent (selenographic) size thresholds per difficulty, in degrees —
// picked from the real data's size distribution (599 features span ~2° to
// 80°+; see IMPLEMENTATION_STEPS.md Step 40 "Open items").
export const DIFFICULTY_MIN_SIZE_DEG = { easy: 15, medium: 5, hard: 0 }

const TYPE_LABELS = {
  crater: 'Crater',
  mare: 'Mare',
  mons: 'Mons',
  lacus: 'Lacus',
  catena: 'Catena',
  sinus: 'Sinus',
  vallis: 'Vallis',
  palus: 'Palus',
  oceanus: 'Oceanus',
}

export function typeLabel(type) {
  return TYPE_LABELS[type] || type
}

// `geom` is a flat (dLon, dLat) offset list with an even number of values —
// either a synthetic 4-corner bounding box, or (for features matched
// against the LROC mare outline dataset) a real N-corner digitized
// boundary. Either way this is the true bounding-box extent of all of it.
function geomSizeDeg(geom) {
  if (!Array.isArray(geom) || geom.length < 8) return 0
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (let i = 0; i < geom.length; i += 2) {
    const x = geom[i]
    const y = geom[i + 1]
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (y < minY) minY = y
    if (y > maxY) maxY = y
  }
  return Math.max(maxX - minX, maxY - minY)
}

// Flattens the raw {type: {name: {lat, lon, size|geom}}} blob (as stored by
// db.js getMeta('moon_features')) into a flat array.
export function flattenMoonFeatures(raw) {
  const list = []
  for (const [type, byName] of Object.entries(raw || {})) {
    for (const [name, rec] of Object.entries(byName || {})) {
      if (!rec || typeof rec.lat !== 'number' || typeof rec.lon !== 'number') continue
      const sizeDeg = typeof rec.size === 'number' ? rec.size : geomSizeDeg(rec.geom)
      list.push({ id: `${type}::${name}`, type, name, lat: rec.lat, lon: rec.lon, sizeDeg, geom: rec.geom || null })
    }
  }
  return list
}

// `geom` stores the feature's boundary as a flat list of (dLon, dLat)
// offset pairs from (feat.lat, feat.lon) — either a synthetic 4-corner
// bounding box, or a real N-corner outline digitized from the LROC mare
// boundary dataset (see data_prep/moon_features.py's _round_feature).
// Resolves those to absolute {lat, lon} corners, or null if the feature
// only has a circular `size` (see flattenMoonFeatures).
export function geomCorners(feat) {
  if (!Array.isArray(feat.geom) || feat.geom.length < 8) return null
  const corners = []
  for (let i = 0; i < feat.geom.length; i += 2) {
    corners.push({ lat: feat.lat + feat.geom[i + 1], lon: feat.lon + feat.geom[i] })
  }
  return corners
}

// Orthographic projection of a selenographic (lat, lon) point onto the
// apparent disc as seen from a given sub-Earth point (subLat, subLon) —
// standard "globe viewed from a point" projection. Returns normalized
// disc coordinates in [-1, 1] (x = east/west, y = north/south, north up)
// plus cosC, the cosine of the point's angular distance from the sub-Earth
// point (1 = center of disc, 0 = limb, negative = far side / not visible).
export function projectPoint(latDeg, lonDeg, subLatDeg, subLonDeg) {
  const phi = latDeg * D2R
  const phi0 = subLatDeg * D2R
  const lambda = (lonDeg - subLonDeg) * D2R
  const cosC = Math.sin(phi0) * Math.sin(phi) + Math.cos(phi0) * Math.cos(phi) * Math.cos(lambda)
  const x = Math.cos(phi) * Math.sin(lambda)
  const y = Math.sin(phi) * Math.cos(phi0) - Math.cos(phi) * Math.sin(phi0) * Math.cos(lambda)
  return { x, y, cosC }
}

// Cosine of the sun's angle at a given selenographic point, given the sun's
// selenographic longitude. The sun's selenographic latitude is small
// (Moon's axial tilt to the ecliptic, <= ~1.6°) and ignored here — fine for
// a schematic map. > 0 = lit, < 0 = dark, near 0 = at the terminator (long
// shadows — surface detail is most visible here).
export function illumCos(latDeg, lonDeg, sunLonDeg) {
  const phi = latDeg * D2R
  const lambda = (lonDeg - sunLonDeg) * D2R
  return Math.cos(phi) * Math.cos(lambda)
}

// Derives the sun's selenographic longitude from the Moon's phase angle.
// At full moon (phase=180) the sub-solar point coincides with the mean
// sub-Earth longitude (whole near side lit); at new moon (phase=0) it's on
// the far side (whole near side dark). This is a schematic approximation
// (real colongitude conventions are more involved) but is internally
// self-consistent and phase-correct at the two reference points.
export function sunLonFromPhase(phaseDeg, subLonDeg) {
  return (((subLonDeg + 180 - phaseDeg) % 360) + 360) % 360
}

// Solves for the sun's selenographic longitude that places a given object a
// signed `offsetDeg` from the terminator: positive = that far into the lit
// side (toward the sub-solar point — larger means flatter, less dramatic
// lighting), negative = that far into the dark side. The sign also picks
// which of the two symmetric terminator crossings (east/west of the object)
// is used — an arbitrary but self-consistent convention (positive = west),
// since this is a synthesized object-relative view, not a real point in the
// lunar cycle. Used by render_moon.mjs to preview a specific feature near
// its own terminator on demand.
export function terminatorSunLonForObject(latDeg, lonDeg, signedOffsetDeg) {
  const latRad = latDeg * D2R
  const offsetRad = Math.abs(signedOffsetDeg) * D2R
  const ratio = Math.max(-1, Math.min(1, Math.sin(offsetRad) / Math.cos(latRad)))
  const deltaLonDeg = Math.acos(ratio) / D2R
  const sign = signedOffsetDeg < 0 ? -1 : 1
  return lonDeg - sign * deltaLonDeg
}

// Real "tonight" viewing conditions for Local scope — the actual sub-Earth
// libration and terminator position for the app's currently-selected date.
export function realViewingConditions(date) {
  const lib = Libration(date)
  const phase = MoonPhase(date)
  return {
    subLat: lib.elat,
    subLon: lib.elon,
    sunLon: sunLonFromPhase(phase, lib.elon),
  }
}

// A random-but-real libration for Global scope — picks a random moment in
// time (within a wide range so all libration extremes are reachable) and
// reads the Moon's actual libration then, rather than fabricating
// elat/elon directly (which risks non-physical combinations). No
// terminator is used in Global scope, so phase/sunLon isn't computed.
export function randomViewingConditions() {
  const randomDate = new Date(Date.now() + (Math.random() - 0.5) * 20 * 365.25 * 24 * 3600 * 1000)
  const lib = Libration(randomDate)
  return { subLat: lib.elat, subLon: lib.elon, sunLon: null }
}

// Fixed mean Earth-facing view — used for Easy difficulty, where precision
// doesn't matter (only big, always-visible features are eligible anyway)
// and a constant view keeps the experience maximally simple.
export function meanViewingConditions() {
  return { subLat: 0, subLon: 0, sunLon: null }
}

// terminatorProminence: 0..1, peaking at the terminator (illumCos == 0) and
// fading to 0 by TERMINATOR_ABS_COS away from it on the lit side — used to
// render terminator-adjacent features more prominently (a schematic
// stand-in for "long shadows reveal detail," not simulated shading).
export function terminatorProminence(cos) {
  if (cos <= 0) return 0
  return Math.max(0, 1 - cos / TERMINATOR_ABS_COS)
}

export function isNearTerminator(cos) {
  return cos > 0 && cos < TERMINATOR_ABS_COS
}
