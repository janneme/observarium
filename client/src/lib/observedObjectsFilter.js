// Shared filter-matching logic for the Observed Objects screen (see
// observed_objects.md) — used both by that screen's own on-screen list and
// by MainScreen's sky-view hide filter, so the two always agree on what
// "matches the current filter" means. Deliberately framework-free (no
// Svelte/store imports) so it stays trivial to reason about and reuse.

// '*' matches any run of characters, '.' matches any single character (kept
// as a literal regex '.', which already means that) — every other regex
// metacharacter is escaped so it's treated literally.
export function wildcardToRegex(pattern) {
  const escaped = String(pattern).replace(/[+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(escaped.replace(/\*/g, '.*'), 'i')
}

export function fallbackLabelFromId(id) {
  const raw = String(id || '')
  if (raw.startsWith('dso_M')) return `M ${Number(raw.slice(5))}`
  if (raw.startsWith('dso_NGC')) return `NGC ${Number(raw.slice(7))}`
  if (raw.startsWith('dso_IC')) return `IC ${Number(raw.slice(6))}`
  if (raw.startsWith('double_WDS')) return `WDS ${raw.slice(10)}`
  if (raw.startsWith('solar_')) {
    const n = raw.slice(6).replace(/_/g, ' ').trim()
    return n ? n[0].toUpperCase() + n.slice(1) : raw
  }
  return raw || 'Unknown object'
}

// "Object" column / Name-filter label. DSOs always show their catalogue
// number (e.g. "NGC 6205"), never a common name like "Hercules Globular
// Cluster" — falls back to name only if no catalogue number is recorded at
// all. Stars/double stars keep the opposite priority: proper name first (so
// a named double star like "Albireo" shows its name), catalogue number as
// fallback.
export function catalogLabel(obj) {
  if (!obj) return ''
  if (obj.type === 'dso') {
    if (obj.m != null) return `M ${obj.m}`
    if (obj.ngc != null) return `NGC ${obj.ngc}`
    if (obj.ic != null) return `IC ${obj.ic}`
    if (obj.caldwell != null) return `C ${obj.caldwell}`
    if (obj.name) return obj.name
    return fallbackLabelFromId(obj.id)
  }
  if (obj.name) return obj.name
  if (obj.bay && obj.constellation) return `${obj.bay} ${obj.constellation}`
  if (obj.flam && obj.constellation) return `${obj.flam} ${obj.constellation}`
  if (obj.m != null) return `M ${obj.m}`
  if (obj.ngc != null) return `NGC ${obj.ngc}`
  if (obj.ic != null) return `IC ${obj.ic}`
  if (obj.caldwell != null) return `C ${obj.caldwell}`
  if (obj.wds) return `WDS ${obj.wds}`
  return fallbackLabelFromId(obj.id)
}

// Object Type filter categories — mirrors the symbol-kind categorization
// already duplicated across ListsScreen/ObservationsScreen/FinderPanel/etc.
// Double stars are a single category regardless of how many components WDS
// catalogues for the system - a WDS entry frequently lists a very faint,
// wide, unrelated-looking extra companion alongside the pair someone
// actually observes, so splitting on component count made a "Double Star"
// filter miss stars people plainly logged as simple doubles.
export function objectTypeKind(obj) {
  if (!obj) return 'generic'
  if (obj.type === 'moon_feature') return 'moon'
  if (obj.type === 'double_star') return 'double_star'
  if (obj.type === 'star') {
    if (obj.dbl) return 'double_star'
    return 'star'
  }
  if (obj.type === 'solar_system_body') return 'solar_system_body'
  const type = String(obj.dsoType || '').toLowerCase()
  if (type === 'open cluster') return 'open_cluster'
  if (type === 'globular cluster') return 'globular_cluster'
  if (type === 'planetary nebula') return 'planetary_nebula'
  if (type === 'spiral galaxy' || type === 'elliptical galaxy' || type === 'galaxy') return 'galaxy'
  if (type === 'dark nebula') return 'dark_nebula'
  if (type === 'galaxy cluster' || type === 'cluster of galaxies') return 'galaxy_cluster'
  if (type === 'quasar' || type === 'qso' || type === 'bl lac') return 'quasar'
  if (type.includes('nebula')) return 'nebula'
  return 'generic'
}

export const OBJECT_TYPE_LABELS = {
  star: 'Star',
  double_star: 'Double Star',
  open_cluster: 'Open Cluster',
  globular_cluster: 'Globular Cluster',
  planetary_nebula: 'Planetary Nebula',
  galaxy: 'Galaxy',
  dark_nebula: 'Dark Nebula',
  galaxy_cluster: 'Galaxy Cluster',
  quasar: 'Quasar',
  nebula: 'Nebula',
  solar_system_body: 'Solar System',
  moon: 'Moon Feature',
  generic: 'Other',
}

// Observation count for an object given the current stats entry (from
// db.js's getObservationStatsByObject) and an optional Year scope — shared
// by the Min/Max-observations filter and the "Number of observations" sort.
export function scopedObservationCount(stat, year) {
  if (!stat) return 0
  if (year == null) return stat.totalCount
  return stat.countsByYear.get(year) || 0
}

// Does `obj` (a resolved catalog object — may be null/undefined if
// unresolved, e.g. a solar-system body or moon feature) match the current
// filter form? `stat` is this object's entry from getObservationStatsByObject.
// An object with no `stat` at all has never been observed, so it can never
// match — this function is only ever meant to select among *observed*
// objects (the Observed Objects screen's own rows are always pre-filtered to
// observed ids, but MainScreen's sky-view hide filter runs this against
// every rendered object, observed or not, and an empty filter form would
// otherwise vacuously match — and thus hide — everything, including objects
// that were never observed at all).
export function objectMatchesFilter(obj, id, filter, stat) {
  if (!stat) return false

  if (filter.telescopeId && !stat?.telescopeIds?.has(filter.telescopeId)) return false

  const year = filter.year != null ? Number(filter.year) : null
  if (year != null && !stat?.countsByYear?.has(year)) return false

  const count = scopedObservationCount(stat, year)
  if (filter.minObs != null && count < Number(filter.minObs)) return false
  if (filter.maxObs != null && count > Number(filter.maxObs)) return false

  if (filter.objectType && objectTypeKind(obj) !== filter.objectType) return false

  const name = String(filter.name || '').trim()
  if (name) {
    const label = catalogLabel(obj) || fallbackLabelFromId(id)
    if (!wildcardToRegex(name).test(label)) return false
  }

  return true
}

export function hasActiveFilter(filter) {
  return !!(
    filter.telescopeId ||
    filter.year != null ||
    filter.minObs != null ||
    filter.maxObs != null ||
    String(filter.name || '').trim() ||
    filter.objectType
  )
}

export function describeFilter(filter, telescopes) {
  const parts = []
  if (filter.telescopeId) {
    const t = (telescopes || []).find((x) => x.id === filter.telescopeId)
    parts.push(`Telescope: ${t?.name || filter.telescopeId}`)
  }
  if (filter.year != null) parts.push(`Year: ${filter.year}`)
  if (filter.minObs != null) parts.push(`Min observations: ${filter.minObs}`)
  if (filter.maxObs != null) parts.push(`Max observations: ${filter.maxObs}`)
  const name = String(filter.name || '').trim()
  if (name) parts.push(`Name: ${name}`)
  if (filter.objectType) parts.push(`Type: ${OBJECT_TYPE_LABELS[filter.objectType] || filter.objectType}`)
  // No criteria set is a deliberate, valid choice ("skip every observed
  // object ever from the sky view"), not an error state — describe it
  // plainly rather than showing an empty description.
  return parts.length ? parts.join(', ') : 'All observed objects'
}
