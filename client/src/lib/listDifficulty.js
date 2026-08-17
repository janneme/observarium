// Difficulty sort for Lists — ranks stars, double stars, and deep sky objects
// against each other on one comparable scale. See lists.md §3.
//
// Object shapes (see db.js/datasync.js ingestion):
// - star: { type: 'star', mag: number|[minMag,maxMag], dbl?: 'p'|'a'|'m'|Array<{pairs}>, pos, ... }
// - dso:  { type: 'dso', mag: number|[mag,...], size: [majorArcmin, minorArcmin], ... }
// - double star: { type: 'double_star', pairs: [{ mag: [mag1, mag2], sep: number|[min,max] }], ... }
//
// A star that is the primary component of a cataloged double star carries a
// truthy `dbl` flag (same convention as ObjectDetails.svelte/TopBar.svelte)
// but usually does NOT embed the pair's separation/companion magnitude
// directly — that lives on a separate `double_star` record found by
// position via db.js's getDoubleStarNear(). `dsById`, when provided below,
// supplies that pre-resolved record per star object id so this module can
// stay synchronous/pure while still scoring split difficulty correctly
// instead of silently falling back to the star's own point-source
// magnitude (which is what a list of double stars added by common name —
// e.g. "Albireo", "Algieba" — was doing: those searches resolve to the
// plain star entry, not the double_star WDS record, since double_star
// records don't carry proper names to search against).

const DOUBLE_STAR_K1 = 0.3 // weight of magnitude difference between components
const DOUBLE_STAR_K2 = 0.15 // weight of the primary's own magnitude

// data_prep's double-star import filter (double_stars.py's _load_systems):
// both components must be <= the catalogue's magnitude limit, separation
// must fall in [min_sep, 60"]. doubleStarDifficulty()'s inputs (separation,
// magDiff, primaryMag) are exactly what this filter already constrains, so
// its min/max can be derived from the filter directly instead of scanning
// every double_star record in the catalogue just to find two endpoints.
const DOUBLE_STAR_IMPORT_MIN_SEP = 2 // arcsec (data_prep's --min-double-star-sep default)
const DOUBLE_STAR_IMPORT_MAX_SEP = 60 // arcsec (hardcoded ceiling in data_prep/double_stars.py)

// catalogueMag: the active magnitude set's limit (e.g. localStorage's
// 'selectedMag') - assumes data_prep's --double-max-mag wasn't overridden
// separately from --max-mag (its default is to match), so this is also the
// double-star magnitude limit for that set.
export function doubleStarDifficultyBounds(catalogueMag) {
  const maxMag = Number.isFinite(catalogueMag) ? catalogueMag : 14
  return {
    // Easiest: widest separation, a bright, evenly-matched pair.
    min: -Math.log10(DOUBLE_STAR_IMPORT_MAX_SEP),
    // Hardest: tightest separation allowed, both components at the faint limit.
    max: -Math.log10(DOUBLE_STAR_IMPORT_MIN_SEP) + DOUBLE_STAR_K1 * maxMag + DOUBLE_STAR_K2 * maxMag,
  }
}

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

// Resolves the list of WDS pairs for a double star's primary, whichever form
// it's carried in — mirrors ObjectDetails.svelte's dblPairs().
export function dblPairs(obj, ds = null) {
  if (obj?.type === 'double_star') return obj.pairs || []
  if (Array.isArray(obj?.dbl)) return obj.dbl.flatMap((entry) => entry.pairs || [])
  if (obj?.dbl && ds) return ds.pairs || []
  return []
}

export function doubleStarDifficulty(obj, ds = null) {
  const pairs = dblPairs(obj, ds)
  const pair = pairs.find((p) => p.comp === 'AB') || pairs[0] || null
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

// Category an object falls into for difficulty purposes. A star that's the
// primary of a cataloged double star (obj.dbl truthy) is scored as a double
// star, not by its own point-source magnitude.
export function difficultyCategory(obj) {
  if (obj?.type === 'dso') return 'dso'
  if (obj?.type === 'double_star' || (obj?.type === 'star' && !!obj?.dbl)) return 'doubleStar'
  return 'star'
}

export function rawDifficulty(obj, ds = null) {
  const category = difficultyCategory(obj)
  if (category === 'dso') return dsoDifficulty(obj)
  if (category === 'doubleStar') return doubleStarDifficulty(obj, ds)
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
// own category, then ordering by that normalized value. `dsById`, if given,
// maps a double-star-primary star's object id to its resolved double_star
// record (see getDoubleStarNear in db.js) — pass it so double stars added to
// the list under their star entry are scored by split difficulty rather
// than raw point-source magnitude.
export function computeListDifficultyOrder(objects, dsById = null) {
  const byCategory = new Map()
  for (const obj of objects) {
    const category = difficultyCategory(obj)
    if (!byCategory.has(category)) byCategory.set(category, [])
    byCategory.get(category).push(obj)
  }

  const normalizedById = new Map()
  for (const items of byCategory.values()) {
    const raws = items.map((obj) => rawDifficulty(obj, dsById?.get(obj.id)))
    const percentiles = percentileRank(raws)
    items.forEach((obj, i) => normalizedById.set(obj.id, percentiles[i]))
  }

  return [...objects].sort((a, b) => (normalizedById.get(a.id) || 0) - (normalizedById.get(b.id) || 0))
}
