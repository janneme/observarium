// Moon Quiz pool construction — see IMPLEMENTATION_STEPS.md Step 40.
//
// Two pools are built per quiz session:
//  - `renderPool`: what MoonCanvas draws. Always the Hard-tier pool for the
//    current scope, regardless of which difficulty is being played, so the
//    map stays visually rich and consistent across difficulties.
//  - `questionPool`: the subset of `renderPool` (Global) or a percentage cut
//    of it (Local) that's actually eligible as a quiz target/distractor at
//    the chosen difficulty.
//
// Both are plain arrays of feature ids (matching the `pool` shape already
// used by quizFramework.js's mastery/progress tracking).
import { LIMB_COS_CUTOFF, isNearTerminator, illumCos, projectPoint, typeBucket } from './moonMap.js'

export const GLOBAL_EASY_CRATERS = 5
export const GLOBAL_EASY_SEA = 15
export const GLOBAL_MEDIUM_CRATERS = 20
export const GLOBAL_MEDIUM_OTHER = 30
export const GLOBAL_HARD_TOTAL = 500

export const LOCAL_MEDIUM_PCT = 0.3
export const LOCAL_HARD_PCT = 1.0

// Minimum viable size of the terminator-filtered base set (before the
// per-difficulty percentage cut) — below this the terminator-proximity
// threshold is widened rather than running a quiz off too few candidates.
export const LOCAL_MIN_POOL_SIZE = 20
export const TERMINATOR_RELAX_FACTOR = 1.5
export const TERMINATOR_RELAX_MAX_STEPS = 6

function byId(features) {
  return features.map((f) => f.id)
}

function rankedBySize(features) {
  return [...features].sort((a, b) => b.sizeDeg - a.sizeDeg)
}

function isVisibleAtMeanView(feat) {
  const p = projectPoint(feat.lat, feat.lon, 0, 0)
  return p.cosC > LIMB_COS_CUTOFF
}

function topN(features, n) {
  return rankedBySize(features).slice(0, n)
}

// Top `n` features by size, all types ranked together — the shared "master"
// pool Local scope narrows further, and Global Hard's own pool directly.
function topOverall(features, n) {
  return topN(features, n)
}

/**
 * Global scope pools for a given difficulty. `allFeatures` is the full
 * flattened catalogue (moonMap.js's flattenMoonFeatures output).
 */
export function buildGlobalPools(allFeatures, difficulty) {
  const visible = allFeatures.filter(isVisibleAtMeanView)
  const hardRenderPool = topOverall(visible, GLOBAL_HARD_TOTAL)

  if (difficulty === 'hard') {
    const ids = byId(hardRenderPool)
    return { questionPool: ids, renderPool: ids }
  }

  const renderPool = byId(hardRenderPool)
  if (difficulty === 'easy') {
    const craters = topN(
      visible.filter((f) => typeBucket(f.type) === 'crater'),
      GLOBAL_EASY_CRATERS,
    )
    const sea = topN(
      visible.filter((f) => typeBucket(f.type) === 'sea'),
      GLOBAL_EASY_SEA,
    )
    return { questionPool: byId([...craters, ...sea]), renderPool }
  }

  // medium
  const craters = topN(
    visible.filter((f) => typeBucket(f.type) === 'crater'),
    GLOBAL_MEDIUM_CRATERS,
  )
  const other = topN(
    visible.filter((f) => typeBucket(f.type) === 'sea' || typeBucket(f.type) === 'ridge'),
    GLOBAL_MEDIUM_OTHER,
  )
  return { questionPool: byId([...craters, ...other]), renderPool }
}

function terminatorFilteredPool(hardPool, viewing) {
  let threshold = undefined // moonMap.js default (TERMINATOR_ABS_COS)
  let filtered = []
  for (let step = 0; step < TERMINATOR_RELAX_MAX_STEPS; step++) {
    filtered = hardPool.filter((f) => {
      const p = projectPoint(f.lat, f.lon, viewing.subLat, viewing.subLon)
      if (p.cosC <= LIMB_COS_CUTOFF) return false
      return isNearTerminator(illumCos(f.lat, f.lon, viewing.sunLon), threshold)
    })
    if (filtered.length >= LOCAL_MIN_POOL_SIZE) break
    threshold = Math.min(1, (threshold ?? 0.3) * TERMINATOR_RELAX_FACTOR)
  }
  return filtered
}

/**
 * Local scope pools (Medium/Hard only). `viewing` is the session-fixed
 * {subLat, subLon, sunLon} for "tonight" (see realViewingConditions).
 */
export function buildLocalPools(allFeatures, difficulty, viewing) {
  const hardUnfiltered = topOverall(allFeatures, GLOBAL_HARD_TOTAL)
  const terminatorNear = terminatorFilteredPool(hardUnfiltered, viewing)
  const renderPool = byId(terminatorNear)

  if (difficulty === 'hard') {
    return { questionPool: renderPool, renderPool }
  }
  const questionPool = byId(topN(terminatorNear, Math.round(terminatorNear.length * LOCAL_MEDIUM_PCT)))
  return { questionPool, renderPool }
}

/**
 * Pick up to `count` distractors sharing the target's broad type bucket,
 * preferring the question pool and falling back to the render pool if that
 * bucket is too thin there.
 */
export function pickDistractors(targetFeature, questionPool, renderPool, featuresById, count = 3) {
  const bucket = typeBucket(targetFeature.type)
  const sameBucket = (id) => id !== targetFeature.id && typeBucket(featuresById.get(id)?.type) === bucket

  const shuffle = (arr) => {
    const out = [...arr]
    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[out[i], out[j]] = [out[j], out[i]]
    }
    return out
  }

  const fromQuestionPool = shuffle(questionPool.filter(sameBucket))
  if (fromQuestionPool.length >= count) return fromQuestionPool.slice(0, count)

  const extra = shuffle(renderPool.filter((id) => sameBucket(id) && !fromQuestionPool.includes(id)))
  return [...fromQuestionPool, ...extra].slice(0, count)
}
