// Constants
const MEASURE_STEP = 0.5
const STEP_MAG_TOLERANCE = 0.2
const MAX_INITIAL_STEPS = 3
const MAX_MOVE_STEPS = 3
const MOVE_STARS_MIN_MAG_DIFF = 1.5
// Guide stars never have to be brighter than this relative to the plan's
// starting magnitude — keeps early hops (near the naked-eye start star, where
// M - MOVE_STARS_MIN_MAG_DIFF is at its strictest) from over-restricting the
// guide-star pool.
const INITIAL_GUIDE_MAG_OFFSET = 0.5
// How many clean initial candidates to evaluate (rather than stopping at the
// first) before committing to the lowest-risk one found — bounds the extra
// DFS cost of looking beyond "first success" for a safer opening jump.
const PHASE1_CLEAN_CANDIDATES_TO_CONSIDER = 10
const MAX_MAG_DIFF = 6.0
const CLOSE_NEIGHBOURHOOD_REL_RADIUS = 0.02
const DSO_MAX_SB = 24.0
const PLAN_SEARCH_RADIUS_FACTOR = 2.5

// Guide-path DFS search
const DFS_NODE_BUDGET = 400
const TRIPLE_FRACTIONS = [1 / 3, 1 / 2, 2 / 3]
const MULTIPLIER_STEP = 0.5
// A user can't reliably eyeball/estimate a large extrapolation multiple —
// cap how far a hop is allowed to overshoot past its aim point.
const MAX_MULTIPLIER = 4
const MONOTONIC_PROGRESS_EPS_REL = 0.02
// Guide-star pool size caps for hop-candidate enumeration — pairs grow O(k^2),
// triples grow O(k^3), so triples get a tighter cap to bound worst-case cost
// in dense bright-star fields.
const MAX_GUIDE_POOL_PAIRS = 40
const MAX_GUIDE_POOL_TRIPLES = 15

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

function wrapRa(ra) {
  return ((ra % 360) + 360) % 360
}

// Shortest-path signed RA delta from ra1 to ra2, in (-180, 180] — needed so
// hop vectors near the 0/360 seam extrapolate the right way instead of the
// long way around the sky.
function raDelta(ra1, ra2) {
  let d = (((ra2 - ra1) % 360) + 360) % 360
  if (d > 180) d -= 360
  return d
}

function midpointRa(ra1, ra2) {
  return wrapRa(ra1 + raDelta(ra1, ra2) / 2)
}

// Point a fraction `frac` of the way from ra1/dec1 to ra2/dec2.
function fracPoint(ra1, dec1, ra2, dec2, frac) {
  return [wrapRa(ra1 + raDelta(ra1, ra2) * frac), dec1 + (dec2 - dec1) * frac]
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

// RA degrees needed to cover an angular radius at a given declination — near
// the poles, a degree of RA covers much less sky than a degree of Dec, so the
// zone search must widen in RA or it silently misses real in-radius stars
// whose RA offset (in raw degrees) exceeds `radius` even though their true
// angular separation doesn't.
function raSearchSpan(dec, radius) {
  const edgeDec = Math.min(89.9, Math.abs(dec) + radius)
  const cosDec = Math.max(Math.cos((edgeDec * Math.PI) / 180), 0.01)
  return radius / cosDec
}

function queryInRadius(buckets, ra, dec, radius) {
  const raSpan = raSearchSpan(dec, radius)
  const zones = _zonesForArea(ra - raSpan, ra + raSpan, dec - radius, dec + radius)
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
  const raSpan = raSearchSpan(dec, radius)
  const zones = _fineZonesForArea(ra - raSpan, ra + raSpan, dec - radius, dec + radius)
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
  const dRa = raDelta(mv.from.pos[0], mv.to.pos[0])
  const dDec = mv.to.pos[1] - mv.from.pos[1]
  return [wrapRa(mv.from.pos[0] + k * dRa), mv.from.pos[1] + k * dDec]
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
// Guide-path DFS
// --------------------------------------------------------------------------

// Multipliers 1, 1.5, 2, 2.5, ... for a hop of length vecLenDeg, capped so the
// extrapolated distance never exceeds one FOV.
function multipliersFor(vecLenDeg, fovDeg) {
  const mults = []
  if (vecLenDeg <= 0) return mults
  for (let m = 1; m <= MAX_MULTIPLIER + 1e-9 && vecLenDeg * m <= fovDeg + 1e-9; m += MULTIPLIER_STEP) {
    mults.push(Math.round(m * 2) / 2)
  }
  return mults
}

// A hop is always centered on a real, visible guide star `from`; the aim point
// is either another real guide star (2-star) or a point interpolated between
// two other guide stars (3-star, `via`) — never a synthetic *origin*, since the
// observer needs a nameable star to center on before moving.
function generateHopCandidates(pairPool, triplePool, fovDeg) {
  const candidates = []

  for (const A of pairPool) {
    for (const B of pairPool) {
      if (B.id === A.id) continue
      const vecLen = angSepDeg(A.pos[0], A.pos[1], B.pos[0], B.pos[1])
      const dRa = raDelta(A.pos[0], B.pos[0])
      const dDec = B.pos[1] - A.pos[1]
      for (const m of multipliersFor(vecLen, fovDeg)) {
        const newRa = wrapRa(A.pos[0] + m * dRa)
        const newDec = A.pos[1] + m * dDec
        if (newDec < -90 || newDec > 90) continue
        candidates.push({ move: { from: A, to: B, multiplier: m }, pos: [newRa, newDec] })
      }
    }
  }

  for (const A of triplePool) {
    for (let i = 0; i < triplePool.length; i++) {
      const B = triplePool[i]
      if (B.id === A.id) continue
      for (let j = i + 1; j < triplePool.length; j++) {
        const C = triplePool[j]
        if (C.id === A.id) continue
        for (const frac of TRIPLE_FRACTIONS) {
          const [viaRa, viaDec] = fracPoint(B.pos[0], B.pos[1], C.pos[0], C.pos[1], frac)
          const vecLen = angSepDeg(A.pos[0], A.pos[1], viaRa, viaDec)
          const dRa = raDelta(A.pos[0], viaRa)
          const dDec = viaDec - A.pos[1]
          for (const m of multipliersFor(vecLen, fovDeg)) {
            const newRa = wrapRa(A.pos[0] + m * dRa)
            const newDec = A.pos[1] + m * dDec
            if (newDec < -90 || newDec > 90) continue
            candidates.push({
              move: {
                from: A,
                to: { pos: [viaRa, viaDec] },
                multiplier: m,
                via: { b: B, c: C, frac },
              },
              pos: [newRa, newDec],
            })
          }
        }
      }
    }
  }

  return candidates
}

// Depth-first, backtracking search for a chain of hops from origin to target.
// Prefers (but does not require) hops that make monotonic progress toward the
// target, so a chain doesn't double back on itself within its own moves.
// Bounded by a fixed node budget rather than exhaustive exploration — this is
// a heuristic, "good chance of succeeding" search, not a complete one.
function findGuidePath(origin, target, maxSteps, guideMaxMag, buckets, fovRadius, fovDeg) {
  if (angSepDeg(origin[0], origin[1], target[0], target[1]) <= fovRadius / 2) return []

  const guideInnerR = fovRadius * 0.85
  const monotonicEps = MONOTONIC_PROGRESS_EPS_REL * fovRadius
  const cellSize = fovRadius / 4

  function snapKey(ra, dec) {
    return `${Math.round(ra / cellSize)},${Math.round(dec / cellSize)}`
  }

  const visited = new Set([snapKey(origin[0], origin[1])])
  let nodeBudget = DFS_NODE_BUDGET

  function recurse(pos, depth, path) {
    if (depth >= maxSteps) return null

    const guidePool = queryInRadius(buckets, pos[0], pos[1], guideInnerR)
      .filter((s) => getStarMag(s) <= guideMaxMag)
      .sort((a, b) => getStarMag(a) - getStarMag(b))
    if (guidePool.length < 2) return null

    const pairPool = guidePool.slice(0, MAX_GUIDE_POOL_PAIRS)
    const triplePool = guidePool.slice(0, MAX_GUIDE_POOL_TRIPLES)
    const candidates = generateHopCandidates(pairPool, triplePool, fovDeg)
    if (candidates.length === 0) return null

    const curDist = angSepDeg(pos[0], pos[1], target[0], target[1])
    for (const c of candidates) {
      c.dist = angSepDeg(c.pos[0], c.pos[1], target[0], target[1])
      c.tier = c.dist < curDist - monotonicEps ? 0 : 1
    }
    candidates.sort((a, b) => a.tier - b.tier || a.dist - b.dist)

    for (const c of candidates) {
      if (nodeBudget <= 0) return null
      const key = snapKey(c.pos[0], c.pos[1])
      if (visited.has(key)) continue
      visited.add(key)
      nodeBudget--

      const newPath = [...path, c.move]
      if (c.dist <= fovRadius / 2) return newPath

      const result = recurse(c.pos, depth + 1, newPath)
      if (result !== null) return result
    }

    return null
  }

  return recurse(origin, 0, [])
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

// Guide stars must be brighter than M - MOVE_STARS_MIN_MAG_DIFF, but never
// stricter than initialMag + INITIAL_GUIDE_MAG_OFFSET — a floor tied to the
// plan's own starting point, not the (possibly much brighter) current M.
function guideMagCeiling(M, initialMag) {
  return Math.max(M - MOVE_STARS_MIN_MAG_DIFF, initialMag + INITIAL_GUIDE_MAG_OFFSET)
}

// Larger multipliers mean longer, less certain extrapolations — they're also
// more likely to land the telescope in an even sparser patch of sky than the
// start star's own neighbourhood, stranding the rest of the chain one step
// later (observed with Mizar: a big first jump reached a spot with no further
// guide stars at all). Used to prefer safer initial jumps over merely-nearest ones.
function moveRisk(moves) {
  let risk = 0
  for (const mv of moves) risk = Math.max(risk, mv.multiplier ?? 1)
  return risk
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

  // getObjectsInArea (db.js, and this test harness's simulator) filters by a
  // flat RA range with no declination correction — widen the RA half-width
  // ourselves near the pole, or a high-declination start star (e.g. Polaris)
  // silently starves itself of most of its own true angular neighbourhood.
  const raSearchHalfWidth = raSearchSpan(startStar.pos[1], planSearchRadius)
  const _raw = await getObjectsInArea(
    startStar.pos[0] - raSearchHalfWidth,
    startStar.pos[0] + raSearchHalfWidth,
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
  let initialDegraded = null
  let overallDegraded = false

  let bestClean = null // { step, endpoint, risk } — lowest-risk clean candidate seen so far
  let cleanCandidatesSeen = 0

  for (const pair of initPairs) {
    if (pair.dist > planSearchRadius) break
    if (cleanCandidatesSeen >= PHASE1_CLEAN_CANDIDATES_TO_CONSIDER) break
    if (!checkMaxMagDiff(pair.centre, initialMag, allBuckets, fovRadius)) continue

    const guideMaxMag = guideMagCeiling(initialMag, initialMag)
    const moves = findGuidePath(
      startStar.pos,
      pair.centre,
      MAX_INITIAL_STEPS,
      guideMaxMag,
      allBuckets,
      fovRadius,
      fovDeg,
    )
    if (moves === null) continue

    const actualEndpoint = computeEndpoint(startStar.pos, moves)
    const [c1, c2] = sortedCandidates(pair.c1, pair.c2)
    if (
      angSepDeg(actualEndpoint[0], actualEndpoint[1], c1.pos[0], c1.pos[1]) > fovRadius ||
      angSepDeg(actualEndpoint[0], actualEndpoint[1], c2.pos[0], c2.pos[1]) > fovRadius
    )
      continue

    // Geometrically valid — classify as clean (keep looking for a safer one,
    // up to the evaluation cap) or degraded (a bright star washes out the
    // actual landing spot; keep searching for a clean alternative, but
    // remember this as a fallback).
    const step = { centre: pair.centre, candidates: [c1, c2], moves }
    if (checkMaxMagDiff(actualEndpoint, initialMag, allBuckets, fovRadius)) {
      cleanCandidatesSeen++
      const risk = moveRisk(moves)
      if (!bestClean || risk < bestClean.risk) {
        bestClean = { step, endpoint: actualEndpoint, risk }
      }
    } else if (!initialDegraded) {
      initialDegraded = { step, endpoint: actualEndpoint }
    }
  }

  if (bestClean) {
    initialStep = bestClean.step
    initialActualEndpoint = bestClean.endpoint
  }

  if (!initialStep) {
    if (!initialDegraded) {
      return { ok: false, reason: 'Could not find a guide path to any initial test position.' }
    }
    // No clean position reachable, but a bright-star-affected one is — offer it
    // as a backup; the user can usually nudge the view to clear the glare.
    initialStep = initialDegraded.step
    initialActualEndpoint = initialDegraded.endpoint
    overallDegraded = true
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
    let moveDegraded = null

    for (const pair of movePairs) {
      if (!checkMaxMagDiff(pair.centre, nextM, allBuckets, fovRadius)) continue

      const guideMaxMag = guideMagCeiling(nextM, initialMag)
      const moves = findGuidePath(
        currentCentre,
        pair.centre,
        MAX_MOVE_STEPS,
        guideMaxMag,
        allBuckets,
        fovRadius,
        fovDeg,
      )
      if (moves === null) continue

      const actualEndpoint = computeEndpoint(currentCentre, moves)
      const [c1, c2] = sortedCandidates(pair.c1, pair.c2)
      if (
        angSepDeg(actualEndpoint[0], actualEndpoint[1], c1.pos[0], c1.pos[1]) > fovRadius ||
        angSepDeg(actualEndpoint[0], actualEndpoint[1], c2.pos[0], c2.pos[1]) > fovRadius
      )
        continue

      const step = { centre: pair.centre, candidates: [c1, c2], moves }
      if (checkMaxMagDiff(actualEndpoint, nextM, allBuckets, fovRadius)) {
        steps.push(step)
        currentCentre = actualEndpoint
        nextM = Math.round((getStarMag(c1) + MEASURE_STEP) * 10) / 10
        moved = true
        break
      } else if (!moveDegraded) {
        moveDegraded = { step, endpoint: actualEndpoint }
      }
    }

    if (!moved) {
      if (moveDegraded) {
        // Same backup logic as phase 1: no clean move found, but a
        // bright-star-affected one is — take it and keep the chain going.
        steps.push(moveDegraded.step)
        currentCentre = moveDegraded.endpoint
        nextM = Math.round((getStarMag(moveDegraded.step.candidates[0]) + MEASURE_STEP) * 10) / 10
        overallDegraded = true
        continue
      }
      break
    }
  }

  if (overallDegraded) {
    return {
      ok: false,
      reason: 'Plan only reachable via a position affected by a nearby bright star.',
      degradedSteps: steps,
    }
  }
  return { ok: true, steps }
}
