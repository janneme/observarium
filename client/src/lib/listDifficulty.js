// Difficulty sort for Lists — ranks stars, double stars, and deep sky objects
// against each other on one comparable scale. See lists.md §3.
//
// Object shapes (see db.js/datasync.js ingestion):
// - star: { type: 'star', mag: number|[minMag,maxMag], ... }
// - dso:  { type: 'dso', mag: number|[mag,...], size: [majorArcmin, minorArcmin], ... }
// - double star: { type: 'double_star', pairs: [{ mag: [mag1, mag2], sep: number|[min,max] }], ... }
//   (pairs[0] is the primary/brightest pair — systems are sorted brightest-first at ingestion)

// Double-star index tuning constants — rough starting values, not yet
// empirically validated against known-difficulty pairs.
const DOUBLE_STAR_K1 = 0.3 // weight of magnitude difference between components
const DOUBLE_STAR_K2 = 0.15 // weight of the primary's own magnitude

const MIN_DSO_AXIS_ARCMIN = 1

function scalarMag(mag) {
  if (typeof mag === 'number') return mag
  if (Array.isArray(mag) && mag.length > 0) return Number(mag[0])
  return NaN
}

function scalarSep(sep) {
  if (typeof sep === 'number') return sep
  if (Array.isArray(sep) && sep.length > 0) return Number(sep[sep.length - 1])
  return NaN
}

export function dsoDifficulty(obj) {
  const size = Array.isArray(obj?.size) ? obj.size : []
  const major = Math.max(Number(size[0]) || 0, MIN_DSO_AXIS_ARCMIN)
  const minor = Math.max(Number(size[1]) || major, MIN_DSO_AXIS_ARCMIN)
  const mag = scalarMag(obj?.mag)
  return (Number.isFinite(mag) ? mag : 0) + 2.5 * Math.log10(major * minor)
}

export function doubleStarDifficulty(obj) {
  const pair = Array.isArray(obj?.pairs) ? obj.pairs[0] : null
  const separation = Math.max(scalarSep(pair?.sep) || 0.01, 0.01)
  const mags = Array.isArray(pair?.mag) ? pair.mag : []
  const primaryMag = Number.isFinite(Number(mags[0])) ? Number(mags[0]) : 0
  const companionMag = Number(mags[1])
  const magDiff = Number.isFinite(companionMag) ? Math.abs(companionMag - primaryMag) : 0
  return -Math.log10(separation) + DOUBLE_STAR_K1 * magDiff + DOUBLE_STAR_K2 * primaryMag
}

export function starDifficulty(obj) {
  const mag = scalarMag(obj?.mag)
  return Number.isFinite(mag) ? mag : 0
}

// Category an object falls into for difficulty purposes.
export function difficultyCategory(obj) {
  if (obj?.type === 'dso') return 'dso'
  if (obj?.type === 'double_star') return 'doubleStar'
  return 'star'
}

export function rawDifficulty(obj) {
  const category = difficultyCategory(obj)
  if (category === 'dso') return dsoDifficulty(obj)
  if (category === 'doubleStar') return doubleStarDifficulty(obj)
  return starDifficulty(obj)
}

// 0 (easiest) .. 100 (hardest), rank-based (ties share the same percentile).
export function percentileRank(values) {
  const n = values.length
  if (n <= 1) return values.map(() => 0)
  const sorted = [...values].sort((a, b) => a - b)
  return values.map((v) => {
    const rank = sorted.indexOf(v)
    return (rank / (n - 1)) * 100
  })
}

// Sorts a mixed list of objects (stars, double stars, DSOs) easiest-first by
// normalizing each object's raw difficulty index to a percentile within its
// own category, then ordering by that normalized value.
export function computeListDifficultyOrder(objects) {
  const byCategory = new Map()
  for (const obj of objects) {
    const category = difficultyCategory(obj)
    if (!byCategory.has(category)) byCategory.set(category, [])
    byCategory.get(category).push(obj)
  }

  const normalizedById = new Map()
  for (const items of byCategory.values()) {
    const raws = items.map(rawDifficulty)
    const percentiles = percentileRank(raws)
    items.forEach((obj, i) => normalizedById.set(obj.id, percentiles[i]))
  }

  return [...objects].sort((a, b) => (normalizedById.get(a.id) || 0) - (normalizedById.get(b.id) || 0))
}
