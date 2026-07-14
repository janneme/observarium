// Constants
const MEASURE_STEP = 0.5
const STEP_MAG_TOLERANCE = 0.2
const MAX_INITIAL_STEPS = 3
const MAX_MOVE_STEPS = 3
const MOVE_STARS_MIN_MAG_DIFF = 1.5
const MAX_MAG_DIFF = 6.0
const CLOSE_NEIGHBOURHOOD_REL_RADIUS = 0.02
const DSO_MAX_SB = 24.0
const BFS_BEAM_WIDTH = 30
const PLAN_SEARCH_RADIUS_FACTOR = 2.5

export const INITIAL_STAR_MAX_MAG = 4.0
export const INITIAL_MAG_MIN = 7.0
export const INITIAL_MAG_MAX = 11.0
export const INITIAL_MAG_STEP = 0.5
export const INITIAL_MAG_RANGE_START_FACTOR = 0.7

// Colour extremes to exclude (must match db.js COLOR_PALETTE indices 0 and 6)
const CLR_BLUEST = '#92b5ff'
const CLR_REDDEST = '#ff8f6b'

const DSO_EXCLUDED_TYPES = new Set([
  'galaxy',
  'spiral galaxy',
  'elliptical galaxy',
  'lenticular galaxy',
  'irregular galaxy',
  'emission nebula',
  'reflection nebula',
  'bright nebula',
  'planetary nebula',
  'supernova remnant',
  'globular cluster',
])

// Coarse zone constants — must match db.js (used for getObjectsInArea zone IDs)
const RA_BUCKET = 5
const DEC_BUCKET = 5
const ZONE_RA_CELLS = 72
const ZONE_DEC_CELLS = 36

function _zoneOf(ra_deg, dec_deg) {
  const ra_cell = Math.floor(ra_deg / RA_BUCKET) % ZONE_RA_CELLS
  const dec_cell = Math.min(ZONE_DEC_CELLS - 1, Math.floor((dec_deg + 90) / DEC_BUCKET))
  return dec_cell * ZONE_RA_CELLS + ra_cell
}

function _zonesForArea(ra_min, ra_max, dec_min, dec_max) {
  const dc_min = Math.max(0, Math.floor((Math.max(-90, dec_min) + 90) / DEC_BUCKET))
  const dc_max = Math.min(ZONE_DEC_CELLS - 1, Math.floor((Math.min(90, dec_max) + 90) / DEC_BUCKET))
  const span = ra_max - ra_min
  const ra0 = ((ra_min % 360) + 360) % 360
  const ra1 = ((ra_max % 360) + 360) % 360
  const rc_min = Math.floor(ra0 / RA_BUCKET)
  const rc_max = Math.floor(ra1 / RA_BUCKET)

  const zones = []
  for (let dc = dc_min; dc <= dc_max; dc++) {
    const base = dc * ZONE_RA_CELLS
    if (span >= 360) {
      for (let rc = 0; rc < ZONE_RA_CELLS; rc++) zones.push(base + rc)
    } else if (rc_min <= rc_max) {
      for (let rc = rc_min; rc <= rc_max; rc++) zones.push(base + rc)
    } else {
      for (let rc = rc_min; rc < ZONE_RA_CELLS; rc++) zones.push(base + rc)
      for (let rc = 0; rc <= rc_max; rc++) zones.push(base + rc)
    }
  }
  return zones
}

// Fine-grain zone constants — 0.1° cells, ~50× finer than coarse.
// Used for isolation queries (radius ≈ 0.033°) to avoid scanning thousands
// of unrelated stars per coarse zone in dense sky regions.
const FINE_CELL_DEG = 0.1
const FINE_RA_CELLS = 3600
const FINE_DEC_CELLS = 1800

function _fineZoneOf(ra_deg, dec_deg) {
  const ra_cell = Math.floor(ra_deg / FINE_CELL_DEG) % FINE_RA_CELLS
  const dec_cell = Math.min(FINE_DEC_CELLS - 1, Math.floor((dec_deg + 90) / FINE_CELL_DEG))
  return dec_cell * FINE_RA_CELLS + ra_cell
}

function _fineZonesForArea(ra_min, ra_max, dec_min, dec_max) {
  const dc_min = Math.max(0, Math.floor((Math.max(-90, dec_min) + 90) / FINE_CELL_DEG))
  const dc_max = Math.min(FINE_DEC_CELLS - 1, Math.floor((Math.min(90, dec_max) + 90) / FINE_CELL_DEG))
  const span = ra_max - ra_min
  const ra0 = ((ra_min % 360) + 360) % 360
  const ra1 = ((ra_max % 360) + 360) % 360
  const rc_min = Math.floor(ra0 / FINE_CELL_DEG)
  const rc_max = Math.floor(ra1 / FINE_CELL_DEG)

  const zones = []
  for (let dc = dc_min; dc <= dc_max; dc++) {
    const base = dc * FINE_RA_CELLS
    if (span >= 360) {
      for (let rc = 0; rc < FINE_RA_CELLS; rc++) zones.push(base + rc)
    } else if (rc_min <= rc_max) {
      for (let rc = rc_min; rc <= rc_max; rc++) zones.push(base + rc)
    } else {
      for (let rc = rc_min; rc < FINE_RA_CELLS; rc++) zones.push(base + rc)
      for (let rc = 0; rc <= rc_max; rc++) zones.push(base + rc)
    }
  }
  return zones
}

function angSepDeg(ra1, dec1, ra2, dec2) {
  const phi1 = (dec1 * Math.PI) / 180
  const phi2 = (dec2 * Math.PI) / 180
  const dPhi = ((dec2 - dec1) * Math.PI) / 180
  const dLam = ((ra2 - ra1) * Math.PI) / 180
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLam / 2) ** 2
  return (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) * 180) / Math.PI
}

function getStarMag(star) {
  return typeof star.mag === 'number' ? star.mag : star.mag[0]
}

function midpointRa(ra1, ra2) {
  let d = (((ra2 - ra1) % 360) + 360) % 360
  if (d > 180) d -= 360
  return (((ra1 + d / 2) % 360) + 360) % 360
}

// --------------------------------------------------------------------------
// Spatial indexes
// --------------------------------------------------------------------------

// Coarse 5°×5° index — used for guide-path BFS and brightness-range checks.
export function buildSpatialIndex(stars) {
  const buckets = new Map()
  for (const star of stars) {
    const z = _zoneOf(star.pos[0], star.pos[1])
    if (!buckets.has(z)) buckets.set(z, [])
    buckets.get(z).push(star)
  }
  return buckets
}

// Fine 0.1°×0.1° index — used for isolation checks where the query radius
// is ~0.033°, making the coarse zones ~50× too large.
function buildFineIndex(stars) {
  const buckets = new Map()
  for (const star of stars) {
    const z = _fineZoneOf(star.pos[0], star.pos[1])
    if (!buckets.has(z)) buckets.set(z, [])
    buckets.get(z).push(star)
  }
  return buckets
}

function queryInRadius(buckets, ra, dec, radius) {
  const zones = _zonesForArea(ra - radius, ra + radius, dec - radius, dec + radius)
  const seen = new Set()
  const results = []
  for (const z of zones) {
    const bucket = buckets.get(z)
    if (!bucket) continue
    for (const star of bucket) {
      if (seen.has(star.id)) continue
      seen.add(star.id)
      if (angSepDeg(ra, dec, star.pos[0], star.pos[1]) <= radius) results.push(star)
    }
  }
  return results
}

// No deduplication — safe because each star is stored in exactly one fine zone,
// and _fineZonesForArea emits each zone ID at most once for non-wraparound boxes.
function queryInFineRadius(fineBuckets, ra, dec, radius) {
  const zones = _fineZonesForArea(ra - radius, ra + radius, dec - radius, dec + radius)
  const results = []
  for (const z of zones) {
    const bucket = fineBuckets.get(z)
    if (!bucket) continue
    for (const star of bucket) {
      if (angSepDeg(ra, dec, star.pos[0], star.pos[1]) <= radius) results.push(star)
    }
  }
  return results
}

// --------------------------------------------------------------------------
// DSO exclusion
// --------------------------------------------------------------------------

function computeSignificantDsos(dsos) {
  const result = []
  for (const dso of dsos) {
    if (!DSO_EXCLUDED_TYPES.has(dso.dsoType)) continue
    const mag = typeof dso.mag === 'number' ? dso.mag : Array.isArray(dso.mag) ? dso.mag[0] : null
    if (mag == null) continue
    const sizeField = dso.size
    if (!sizeField) continue
    let a, b
    if (Array.isArray(sizeField)) {
      a = sizeField[0] / 2
      b = sizeField[1] / 2
    } else {
      a = sizeField / 2
      b = sizeField / 2
    }
    if (a <= 0 || b <= 0) continue
    const SB = mag + 2.5 * Math.log10(Math.PI * (a * 30) * (b * 30))
    if (SB < DSO_MAX_SB) result.push({ pos: dso.pos, radiusDeg: a / 60 })
  }
  return result
}

// --------------------------------------------------------------------------
// Candidate qualification
// --------------------------------------------------------------------------

function isIsolated(star, fineBuckets, isolRadius) {
  const mag = getStarMag(star)
  const neighbors = queryInFineRadius(fineBuckets, star.pos[0], star.pos[1], isolRadius)
  for (const n of neighbors) {
    if (n.id === star.id) continue
    if (getStarMag(n) < mag) return false
  }
  return true
}

function notInDso(star, significantDsos, margin) {
  for (const dso of significantDsos) {
    if (angSepDeg(star.pos[0], star.pos[1], dso.pos[0], dso.pos[1]) < dso.radiusDeg + margin) return false
  }
  return true
}

// Binary search: first index where getStarMag(sortedStars[i]) >= magLo
function _lowerBound(sortedStars, magLo) {
  let lo = 0,
    hi = sortedStars.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (getStarMag(sortedStars[mid]) < magLo) lo = mid + 1
    else hi = mid
  }
  return lo
}

// sortedStars must be sorted by mag ascending; fineBuckets is the fine-grain index.
function getCandidates(M, sortedStars, fineBuckets, fovDeg, significantDsos) {
  const isolRadius = CLOSE_NEIGHBOURHOOD_REL_RADIUS * fovDeg
  const dsoMargin = CLOSE_NEIGHBOURHOOD_REL_RADIUS * fovDeg
  const magLo = M - STEP_MAG_TOLERANCE
  const magHi = M + STEP_MAG_TOLERANCE
  const results = []
  const start = _lowerBound(sortedStars, magLo)
  for (let i = start; i < sortedStars.length; i++) {
    const star = sortedStars[i]
    const mag = getStarMag(star)
    if (mag > magHi) break
    if (star.varType) continue
    if (star.clr === CLR_BLUEST || star.clr === CLR_REDDEST) continue
    if (!isIsolated(star, fineBuckets, isolRadius)) continue
    if (!notInDso(star, significantDsos, dsoMargin)) continue
    results.push(star)
  }
  return results
}

// A hop lands at the `to` guide star (k=1 means "center on the star you can
// see"); for k>1 it extrapolates (k-1) more hops past it. Each move is
// self-contained — the endpoint depends only on the *last* move's own
// from/to/multiplier, not on where earlier hops in the chain landed.
function computeEndpoint(origin, moves) {
  if (moves.length === 0) return origin
  const mv = moves[moves.length - 1]
  const k = mv.multiplier ?? 1
  const dRa = mv.to.pos[0] - mv.from.pos[0]
  const dDec = mv.to.pos[1] - mv.from.pos[1]
  return [(((mv.to.pos[0] + (k - 1) * dRa) % 360) + 360) % 360, mv.to.pos[1] + (k - 1) * dDec]
}

// After finding a guide path, the last hop's `to` star lands within fovRadius of the
// BFS position, which is up to fovRadius/2 from `centre` — so it can slip past
// checkMaxMagDiff's fovRadius search. Verify it explicitly.
function lastHopClear(moves, centre, M, fovRadius) {
  if (moves.length === 0) return true
  const lastTo = moves[moves.length - 1].to
  const dist = angSepDeg(lastTo.pos[0], lastTo.pos[1], centre[0], centre[1])
  return dist >= fovRadius || M - getStarMag(lastTo) <= MAX_MAG_DIFF
}

function checkMaxMagDiff(centre, M, buckets, fovRadius) {
  const nearby = queryInRadius(buckets, centre[0], centre[1], fovRadius)
  if (nearby.length === 0) return true
  let brightestMag = Infinity
  for (const s of nearby) {
    const m = getStarMag(s)
    if (m < brightestMag) brightestMag = m
  }
  return M - brightestMag <= MAX_MAG_DIFF
}

// --------------------------------------------------------------------------
// BFS guide path
// --------------------------------------------------------------------------

function findGuidePath(origin, target, maxSteps, guideMaxMag, buckets, fovRadius, fovDeg) {
  if (angSepDeg(origin[0], origin[1], target[0], target[1]) <= fovRadius / 2) return []

  const cellSize = fovRadius / 4

  function snapKey(ra, dec) {
    return `${Math.round(ra / cellSize)},${Math.round(dec / cellSize)}`
  }

  const visited = new Set([snapKey(origin[0], origin[1])])
  let beam = [{ pos: origin, path: [] }]

  for (let depth = 0; depth < maxSteps; depth++) {
    const children = []

    for (const state of beam) {
      const [pRa, pDec] = state.pos

      const guideInnerR = fovRadius * 0.85
      const guideS = queryInRadius(buckets, pRa, pDec, guideInnerR).filter((s) => getStarMag(s) <= guideMaxMag)

      for (const sS of guideS) {
        const guideE = queryInRadius(buckets, sS.pos[0], sS.pos[1], fovRadius).filter(
          (s) => getStarMag(s) <= guideMaxMag && s.id !== sS.id,
        )

        for (const eE of guideE) {
          // Both guide stars must be clearly interior to the FOV (not at the edge)
          if (angSepDeg(pRa, pDec, eE.pos[0], eE.pos[1]) > guideInnerR) continue

          const sep = angSepDeg(sS.pos[0], sS.pos[1], eE.pos[0], eE.pos[1])

          for (const k of [1, 2, 3]) {
            if (sep * k > 2 * fovDeg) continue

            const dRa = eE.pos[0] - sS.pos[0]
            const dDec = eE.pos[1] - sS.pos[1]
            // Anchor the hop at the "to" guide star (k=1 = center directly on it),
            // not at the current position — `sS` is just a nearby reference star,
            // not necessarily where the view is actually centered.
            const newRa = (((eE.pos[0] + (k - 1) * dRa) % 360) + 360) % 360
            const newDec = eE.pos[1] + (k - 1) * dDec

            if (newDec < -90 || newDec > 90) continue

            const key = snapKey(newRa, newDec)
            if (visited.has(key)) continue

            const dist = angSepDeg(newRa, newDec, target[0], target[1])

            if (dist <= fovRadius / 2) {
              return [...state.path, { from: sS, to: eE, multiplier: k }]
            }

            visited.add(key)
            children.push({
              pos: [newRa, newDec],
              path: [...state.path, { from: sS, to: eE, multiplier: k }],
              dist,
            })
          }
        }
      }
    }

    if (children.length === 0) break
    children.sort((a, b) => a.dist - b.dist)
    beam = children.slice(0, BFS_BEAM_WIDTH)
  }

  return null
}

// --------------------------------------------------------------------------
// Pair helpers
// --------------------------------------------------------------------------

function buildPairs(candidates, fovRadius, refPos) {
  const cBuckets = new Map()
  for (const c of candidates) {
    const z = _zoneOf(c.pos[0], c.pos[1])
    if (!cBuckets.has(z)) cBuckets.set(z, [])
    cBuckets.get(z).push(c)
  }

  const seen = new Set()
  const pairs = []
  for (const c1 of candidates) {
    const nearby = queryInRadius(cBuckets, c1.pos[0], c1.pos[1], 2 * fovRadius)
    for (const c2 of nearby) {
      if (c2.id === c1.id) continue
      const key = c1.id < c2.id ? `${c1.id}|${c2.id}` : `${c2.id}|${c1.id}`
      if (seen.has(key)) continue
      seen.add(key)
      const midRa = midpointRa(c1.pos[0], c2.pos[0])
      const midDec = (c1.pos[1] + c2.pos[1]) / 2
      const centre = [midRa, midDec]
      const dist = angSepDeg(refPos[0], refPos[1], midRa, midDec)
      pairs.push({ c1, c2, centre, dist })
    }
  }
  pairs.sort((a, b) => a.dist - b.dist)
  return pairs
}

function sortedCandidates(c1, c2) {
  // Faintest (highest magnitude number) first → C1
  return getStarMag(c1) >= getStarMag(c2) ? [c1, c2] : [c2, c1]
}

// --------------------------------------------------------------------------
// Main export
// --------------------------------------------------------------------------

export async function generatePlan({ getObjectsInArea, dsos, startStar, telescope, eyepiece, initialMag }) {
  const fovDeg = (eyepiece.fov * eyepiece.focalLength) / telescope.focalLength
  const fovRadius = fovDeg / 2
  const planSearchRadius = PLAN_SEARCH_RADIUS_FACTOR * fovDeg

  const significantDsos = computeSignificantDsos(dsos)

  const theoreticalMax = 2.1 + 5 * Math.log10(telescope.diameter)
  const planCeiling = theoreticalMax

  const _raw = await getObjectsInArea(
    startStar.pos[0] - planSearchRadius,
    startStar.pos[0] + planSearchRadius,
    startStar.pos[1] - planSearchRadius,
    startStar.pos[1] + planSearchRadius,
    planCeiling + STEP_MAG_TOLERANCE,
  )
  const allLocalStars = _raw.filter((o) => o.type === 'star')

  allLocalStars.sort((a, b) => getStarMag(a) - getStarMag(b))

  const allBuckets = buildSpatialIndex(allLocalStars)
  const allFineBuckets = buildFineIndex(allLocalStars)

  // Phase 1: find initial measurement position
  const initCandidates = getCandidates(initialMag, allLocalStars, allFineBuckets, fovDeg, significantDsos)

  if (initCandidates.length < 2) {
    return { ok: false, reason: 'Not enough suitable test stars at the initial magnitude.' }
  }

  const initPairs = buildPairs(initCandidates, fovRadius, startStar.pos)

  if (initPairs.length === 0) {
    return {
      ok: false,
      reason: 'No pair of test stars within one FOV found for the initial magnitude.',
    }
  }

  let initialStep = null
  let initialActualEndpoint = null

  for (const pair of initPairs) {
    if (pair.dist > planSearchRadius) break
    if (!checkMaxMagDiff(pair.centre, initialMag, allBuckets, fovRadius)) continue

    const guideMaxMag = initialMag - MOVE_STARS_MIN_MAG_DIFF
    const moves = findGuidePath(
      startStar.pos,
      pair.centre,
      MAX_INITIAL_STEPS,
      guideMaxMag,
      allBuckets,
      fovRadius,
      fovDeg,
    )

    if (moves !== null && lastHopClear(moves, pair.centre, initialMag, fovRadius)) {
      const actualEndpoint = computeEndpoint(startStar.pos, moves)
      const [c1, c2] = sortedCandidates(pair.c1, pair.c2)
      if (
        angSepDeg(actualEndpoint[0], actualEndpoint[1], c1.pos[0], c1.pos[1]) > fovRadius ||
        angSepDeg(actualEndpoint[0], actualEndpoint[1], c2.pos[0], c2.pos[1]) > fovRadius
      )
        continue
      initialStep = { centre: pair.centre, candidates: [c1, c2], moves }
      initialActualEndpoint = actualEndpoint
      break
    }
  }

  if (!initialStep) {
    return { ok: false, reason: 'Could not find a guide path to any initial test position.' }
  }

  const steps = [initialStep]
  let currentCentre = initialActualEndpoint ?? initialStep.centre
  let nextM = Math.round((getStarMag(initialStep.candidates[0]) + MEASURE_STEP) * 10) / 10

  // Phase 2: step chain
  while (nextM <= planCeiling + STEP_MAG_TOLERANCE) {
    const candidates = getCandidates(nextM, allLocalStars, allFineBuckets, fovDeg, significantDsos)

    const atCentre = candidates.filter(
      (s) => angSepDeg(currentCentre[0], currentCentre[1], s.pos[0], s.pos[1]) <= fovRadius,
    )

    if (atCentre.length >= 2 && checkMaxMagDiff(currentCentre, nextM, allBuckets, fovRadius)) {
      atCentre.sort((a, b) => getStarMag(b) - getStarMag(a))
      const [c1, c2] = atCentre
      steps.push({ centre: currentCentre, candidates: [c1, c2], moves: [] })
      nextM = Math.round((getStarMag(c1) + MEASURE_STEP) * 10) / 10
      continue
    }

    const reachable = candidates.filter(
      (s) => angSepDeg(currentCentre[0], currentCentre[1], s.pos[0], s.pos[1]) <= planSearchRadius,
    )
    const brightThreshold = nextM - MAX_MAG_DIFF
    const brightStars = allLocalStars.filter((s) => getStarMag(s) < brightThreshold)
    const brightBuckets = buildFineIndex(brightStars)
    const safeReachable = reachable.filter(
      (s) => queryInFineRadius(brightBuckets, s.pos[0], s.pos[1], fovRadius).length === 0,
    )
    const movePairs = buildPairs(safeReachable, fovRadius, currentCentre)
    let moved = false

    for (const pair of movePairs) {
      if (!checkMaxMagDiff(pair.centre, nextM, allBuckets, fovRadius)) continue

      const guideMaxMag = nextM - MOVE_STARS_MIN_MAG_DIFF
      const moves = findGuidePath(
        currentCentre,
        pair.centre,
        MAX_MOVE_STEPS,
        guideMaxMag,
        allBuckets,
        fovRadius,
        fovDeg,
      )

      if (moves !== null && lastHopClear(moves, pair.centre, nextM, fovRadius)) {
        const actualEndpoint = computeEndpoint(currentCentre, moves)
        const [c1, c2] = sortedCandidates(pair.c1, pair.c2)
        if (
          angSepDeg(actualEndpoint[0], actualEndpoint[1], c1.pos[0], c1.pos[1]) > fovRadius ||
          angSepDeg(actualEndpoint[0], actualEndpoint[1], c2.pos[0], c2.pos[1]) > fovRadius
        )
          continue
        steps.push({ centre: pair.centre, candidates: [c1, c2], moves })
        currentCentre = actualEndpoint
        nextM = Math.round((getStarMag(c1) + MEASURE_STEP) * 10) / 10
        moved = true
        break
      }
    }

    if (!moved) break
  }

  return { ok: true, steps }
}
