// Deep Sky Quiz pool/distractor construction — see deep_sky_quiz.md.
//
// Pure logic, kept out of the Svelte screen so it's independently testable
// (mirrors the moonQuizPools.js / StarQuizScreen.svelte split).

// Easy is Messier-only (no NGC) — Messier objects are the well-known,
// commonly-taught set, so restricting Easy to them keeps the quiz beginner-
// friendly.
export const EASY_POOL_SIZE = 30
export const MEDIUM_NGC_POOL_SIZE = 30
export const HARD_NGC_POOL_SIZE = 200

export const QUESTION_COUNTS = { easy: 15, medium: 30, hard: 50 }

// Subtype buckets for the type-2 (image) distractor-exclusion rule. Clusters
// split into globular/open; galaxies split into spiral/elliptical/plain
// "galaxy" (the data has no distinct "irregular" subtype — unclassified
// galaxies get their own bucket rather than being merged into spiral or
// elliptical). Nebulae share one bucket that's exempt from the exclusion
// check entirely — visually distinct enough not to need it.
const SUBTYPE_BUCKET = {
  'spiral galaxy': 'spiral galaxy',
  'elliptical galaxy': 'elliptical galaxy',
  galaxy: 'galaxy',
  'globular cluster': 'globular cluster',
  'open cluster': 'open cluster',
  'emission nebula': 'nebula',
  'reflection nebula': 'nebula',
  'planetary nebula': 'nebula',
}

export function subtypeBucket(dsoType) {
  return SUBTYPE_BUCKET[dsoType] || dsoType || 'unknown'
}

function isNonMessierOpenClusterWithoutImage(dso, hasImage) {
  return dso.dsoType === 'open cluster' && dso.m == null && !hasImage(dso.id)
}

function firstMag(dso) {
  return typeof dso.mag === 'number' ? dso.mag : dso.mag?.[0]
}

function byMagAscending(a, b) {
  return firstMag(a) - firstMag(b)
}

/**
 * Builds the eligible object pool for a difficulty level.
 * `dsos` is a flat array of DSO objects (as returned by getSearchIndex,
 * filtered to type === 'dso'). `hasImage` is a (id) => boolean predicate.
 * Returns an array of object ids.
 */
export function buildEligiblePool(dsos, difficulty, hasImage) {
  const eligible = dsos.filter((d) => !isNonMessierOpenClusterWithoutImage(d, hasImage))

  if (difficulty === 'easy') {
    return eligible
      .filter((d) => d.m != null)
      .sort(byMagAscending)
      .slice(0, EASY_POOL_SIZE)
      .map((d) => d.id)
  }

  const messier = eligible.filter((d) => d.m != null)
  const nonMessierNgc = eligible.filter((d) => d.m == null).sort(byMagAscending)
  const ngcCap = difficulty === 'hard' ? HARD_NGC_POOL_SIZE : MEDIUM_NGC_POOL_SIZE
  return [...messier, ...nonMessierNgc.slice(0, ngcCap)].map((d) => d.id)
}

function angSepDeg([ra1, dec1], [ra2, dec2]) {
  const r = Math.PI / 180
  return (
    Math.acos(
      Math.max(
        -1,
        Math.min(
          1,
          Math.sin(dec1 * r) * Math.sin(dec2 * r) + Math.cos(dec1 * r) * Math.cos(dec2 * r) * Math.cos((ra2 - ra1) * r),
        ),
      ),
    ) / r
  )
}

function shuffle(arr) {
  const out = [...arr]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

/**
 * Type-1 (Object position) distractors: excludes any candidate within
 * minSepDeg of the target's position, so visually confusable close pairs
 * (e.g. M81/M82) never appear together as quizzed object + distractor.
 */
export function pickPositionDistractors(targetId, pool, dsosById, minSepDeg, count = 3) {
  const target = dsosById.get(targetId)
  if (!target) return []
  const candidates = pool.filter((id) => {
    if (id === targetId) return false
    const c = dsosById.get(id)
    if (!c || !Array.isArray(c.pos)) return false
    return angSepDeg(target.pos, c.pos) > minSepDeg
  })
  return shuffle(candidates).slice(0, count)
}

/**
 * Type-2 (Recognize by Image) distractors: every tile shown (target +
 * distractors) needs a real image, and distractors must be a different
 * subtype bucket than the target (nebula bucket is exempt from this check).
 */
export function pickImageDistractors(targetId, pool, dsosById, hasImageSet, count = 3) {
  const target = dsosById.get(targetId)
  if (!target) return []
  const targetBucket = subtypeBucket(target.dsoType)
  const candidates = pool.filter((id) => {
    if (id === targetId || !hasImageSet.has(id)) return false
    const c = dsosById.get(id)
    if (!c) return false
    if (targetBucket === 'nebula') return true
    return subtypeBucket(c.dsoType) !== targetBucket
  })
  return shuffle(candidates).slice(0, count)
}

/**
 * Type-3 (catalogue number <-> name) distractors: plain random pick, no
 * visual-confusability constraint since there's no rendered view to confuse.
 */
export function pickNameDistractors(targetId, pool, count = 3) {
  const candidates = pool.filter((id) => id !== targetId)
  return shuffle(candidates).slice(0, count)
}
