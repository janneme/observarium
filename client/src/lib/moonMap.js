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
  vallis: 'Vallis',
  palus: 'Palus',
  oceanus: 'Oceanus',
}

export function typeLabel(type) {
  return TYPE_LABELS[type] || type
}

// `geom` is a list of drawable layers, each a style-tagged path string:
// "S <STYLE> M<lat>,<lon> L<dlat>,<dlon> ... Z" — the first vertex absolute,
// every following vertex a delta from the previous one (SVG relative-lineto
// convention). STYLE tells the client which generic drawing method to use
// (FILLED: two-pass edge+fill boundary; RAISED: crater-style rim
// treatment) — chosen pipeline-side from feature type, not re-derived here.
// See data_prep/moon_features.py's _round_feature / moon_pipeline.md.
export function parseGeomLayers(geom) {
  if (!Array.isArray(geom)) return []
  const layers = []
  for (const str of geom) {
    const tokens = String(str).trim().split(/\s+/)
    if (tokens[0] !== 'S') continue
    const style = tokens[1]
    const points = []
    let lat = 0
    let lon = 0
    for (let i = 2; i < tokens.length; i++) {
      const tok = tokens[i]
      if (tok === 'Z') break
      const cmd = tok[0]
      const [a, b] = tok
        .slice(1)
        .split(',')
        .map(Number)
      if (cmd === 'M') {
        lat = a
        lon = b
      } else if (cmd === 'L') {
        lat += a
        lon += b
      } else {
        continue
      }
      points.push({ lat, lon })
    }
    layers.push({ style, points })
  }
  return layers
}

// Bounding-box extent (degrees) of a layer's points — used as the
// feature's apparent size for difficulty filtering and point-feature
// radius, same role the old flat `size`/`geom` bbox scalar played.
function layerExtentDeg(points) {
  let minLat = Infinity
  let maxLat = -Infinity
  let minLon = Infinity
  let maxLon = -Infinity
  for (const p of points) {
    if (p.lat < minLat) minLat = p.lat
    if (p.lat > maxLat) maxLat = p.lat
    if (p.lon < minLon) minLon = p.lon
    if (p.lon > maxLon) maxLon = p.lon
  }
  return Math.max(maxLat - minLat, maxLon - minLon)
}

// Flattens the raw {type: {name: {lat, lon, geom}}} blob (as stored by
// db.js getMeta('moon_features')) into a flat array. `geom` layers are
// parsed once here (not per canvas frame) since they're pure static data.
export function flattenMoonFeatures(raw) {
  const list = []
  for (const [type, byName] of Object.entries(raw || {})) {
    for (const [name, rec] of Object.entries(byName || {})) {
      if (!rec || typeof rec.lat !== 'number' || typeof rec.lon !== 'number') continue
      const layers = parseGeomLayers(rec.geom)
      const sizeDeg = layers.length ? layerExtentDeg(layers[0].points) : 0
      list.push({ id: `${type}::${name}`, type, name, lat: rec.lat, lon: rec.lon, sizeDeg, layers })
    }
  }
  return list
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

export function isNearTerminator(cos) {
  return cos > 0 && cos < TERMINATOR_ABS_COS
}

// Point features (craters etc.) fade out with distance from the terminator
// — 1 (fully visible) right at the terminator (illumCos == 0), dropping
// toward CRATER_FADE_MIN_ALPHA well before the sub-solar point (illumCos ==
// 1). A schematic stand-in for "long shadows reveal detail near the
// terminator, washed out under fuller sunlight" — only meaningful when a
// terminator view is active; MoonCanvas.svelte leaves point features at a
// fixed alpha otherwise. CRATER_FADE_POWER > 1 makes the drop-off front-
// loaded (steep near the terminator, tapering as it nears the floor)
// rather than spread evenly across the whole lit hemisphere.
export const CRATER_FADE_MIN_ALPHA = 0.12
const CRATER_FADE_POWER = 3

export function craterFadeAlpha(cos) {
  const t = Math.max(0, Math.min(1, cos))
  return CRATER_FADE_MIN_ALPHA + (1 - CRATER_FADE_MIN_ALPHA) * Math.pow(1 - t, CRATER_FADE_POWER)
}
