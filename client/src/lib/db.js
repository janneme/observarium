import { openDB as idbOpenDB } from 'idb'
import { SEARCH_ALIASES } from './customObjects.js'

const DB_NAME = 'observarium'
const DB_VERSION = 5

const RA_BUCKET = 5
const DEC_BUCKET = 5
export const ZONE_RA_CELLS = 72 // 360 / RA_BUCKET
export const ZONE_DEC_CELLS = 36 // 180 / DEC_BUCKET

// Colour palette: index 0–7, must match COLOR_PALETTE in data_prep/stars.py.
export const COLOR_PALETTE = [
  '#92b5ff', // 0 O
  '#b2c5ff', // 1 B
  '#cad8ff', // 2 A
  '#f8f7ff', // 3 F
  '#fff4e8', // 4 G
  '#ffd2a1', // 5 K
  '#ff8f6b', // 6 M
  '#ffffff', // 7 default
]

// Stars with mag ≤ T1_MAG_LIMIT live in the in-memory cache.
// Stars with mag > T1_MAG_LIMIT are fetched from IDB zones_t2 on demand.
export const T1_MAG_LIMIT = 9.0

// Compute sky-zone integer (0–2591) from equatorial coordinates.
export function computeZone(ra_deg, dec_deg) {
  const ra_cell = Math.floor(ra_deg / RA_BUCKET) % ZONE_RA_CELLS
  const dec_cell = Math.min(ZONE_DEC_CELLS - 1, Math.floor((dec_deg + 90) / DEC_BUCKET))
  return dec_cell * ZONE_RA_CELLS + ra_cell
}

let _db = null
let _dbPromise = null

function _resetDb() {
  _db = null
  _dbPromise = null
}

async function getDB() {
  if (_db) return _db
  if (!_dbPromise) {
    _dbPromise = idbOpenDB(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion, _newVersion, transaction) {
        if (oldVersion < 1) {
          db.createObjectStore('objects', { keyPath: 'id' })
          db.createObjectStore('images', { keyPath: 'catalogueId' })
          db.createObjectStore('observations', { keyPath: 'date' })
          db.createObjectStore('meta', { keyPath: 'key' })
        }
        if (oldVersion < 2) {
          transaction.objectStore('objects').createIndex('by_zone', 'zone')
        }
        if (oldVersion < 3) {
          db.createObjectStore('zones_t2', { keyPath: 'zone' })
          // Stale star records from the objects store must be removed; they will
          // be reloaded as CSV blobs on next data download.
          transaction.objectStore('objects').clear()
        }
        if (oldVersion < 5) {
          // Guard needed: DB may already be at version 4 without this store.
          if (!db.objectStoreNames.contains('stars_named')) {
            db.createObjectStore('stars_named', { keyPath: 'id' })
          }
        }
      },
      // Another connection (e.g. another tab) is trying to upgrade the DB.
      // Close our end so the upgrade can proceed; next getDB() reopens.
      blocking() {
        if (_db) _db.close()
        _resetDb()
      },
      // The browser forcibly closed the connection (storage error, DevTools
      // database deletion, etc.).  Clear the stale reference so next getDB()
      // opens a fresh connection.
      terminated() {
        _resetDb()
      },
    }).then(
      (db) => {
        _db = db
        _dbPromise = null
        return db
      },
      (err) => {
        _dbPromise = null
        throw err
      },
    )
  }
  return _dbPromise
}

// --------------------------------------------------------------------------
// Tier-1 in-memory cache
// --------------------------------------------------------------------------

let _tier1Cache = null // null until loaded; [] means loaded but empty

function _parseMag(raw) {
  if (raw.includes(':')) {
    const [a, b] = raw.split(':')
    return [parseFloat(a), parseFloat(b)]
  }
  return parseFloat(raw)
}

function _parseT1Csv(csv) {
  const lines = csv.split('\n')
  // header: ra,de,mg,cl,hp,hd,sp,ds,pr,pd,fl,by,db,nm,nt,sm,cn,vt,vp,an
  const stars = []
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i]
    if (!line) continue
    const c = line.split(',')
    const ra = parseFloat(c[0])
    const dec = parseFloat(c[1])
    const mag = _parseMag(c[2])
    const colour = COLOR_PALETTE[parseInt(c[3], 10)] || COLOR_PALETTE[7]
    const hip = c[4] ? parseInt(c[4], 10) : null
    const hd = c[5] ? parseInt(c[5], 10) : null
    const id = hip ? `star_HIP${hip}` : hd ? `star_HD${hd}` : null
    if (!id) continue
    const star = {
      id,
      type: 'star',
      pos: [ra, dec],
      mag,
      clr: colour,
      zone: computeZone(ra, dec),
    }
    if (hip) star.hip = hip
    if (hd) star.hd = hd
    if (c[6]) star.spect = c[6]
    if (c[7]) star.dist = parseFloat(c[7])
    if (c[8]) star.pm_ra = parseFloat(c[8])
    if (c[9]) star.pm_dec = parseFloat(c[9])
    if (c[10]) star.flam = parseInt(c[10], 10)
    if (c[11]) star.bay = c[11]
    if (c[12]) star.dbl = c[12]
    if (c[13]) star.name = c[13]
    if (c[14]) star.note = c[14]
    if (c[15]) star.smr = c[15]
    if (c[16]) star.constellation = c[16]
    if (c[17]) star.varType = c[17]
    if (c[18]) star.varPeriod = parseFloat(c[18])
    if (c[19]) star.altNames = c[19].split(';')
    stars.push(star)
  }
  return stars
}

function _parseT2Csv(csv) {
  // rows: z,ra,de,mg,cl,hp,hd,sp,ds,pr,pd  (no header in zone blob)
  const lines = csv.split('\n')
  const stars = []
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (!line) continue
    const c = line.split(',')
    const ra = parseFloat(c[1])
    const dec = parseFloat(c[2])
    const mag = _parseMag(c[3])
    const colour = COLOR_PALETTE[parseInt(c[4], 10)] || COLOR_PALETTE[7]
    const hip = c[5] ? parseInt(c[5], 10) : null
    const hd = c[6] ? parseInt(c[6], 10) : null
    const id = hip ? `star_HIP${hip}` : hd ? `star_HD${hd}` : `star_t2_${c[1]}_${c[2]}`
    const star = {
      id,
      type: 'star',
      pos: [ra, dec],
      mag,
      clr: colour,
      zone: parseInt(c[0], 10),
    }
    if (hip) star.hip = hip
    if (hd) star.hd = hd
    if (c[7]) star.spect = c[7]
    if (c[8]) star.dist = parseFloat(c[8])
    if (c[9]) star.pm_ra = parseFloat(c[9])
    if (c[10]) star.pm_dec = parseFloat(c[10])
    stars.push(star)
  }
  return stars
}

// Like _parseT2Csv but skips stars without HIP/HD — used to populate stars_named.
function _parseT2CsvNamedOnly(csv) {
  const lines = csv.split('\n')
  const stars = []
  for (const line of lines) {
    if (!line) continue
    const c = line.split(',')
    if (!c[5] && !c[6]) continue
    const hip = c[5] ? parseInt(c[5], 10) : null
    const hd = c[6] ? parseInt(c[6], 10) : null
    const id = hip ? `star_HIP${hip}` : `star_HD${hd}`
    const star = {
      id,
      type: 'star',
      pos: [parseFloat(c[1]), parseFloat(c[2])],
      mag: _parseMag(c[3]),
      clr: COLOR_PALETTE[parseInt(c[4], 10)] || COLOR_PALETTE[7],
      zone: parseInt(c[0], 10),
    }
    if (hip) star.hip = hip
    if (hd) star.hd = hd
    if (c[7]) star.spect = c[7]
    stars.push(star)
  }
  return stars
}

async function _ensureTier1Loaded() {
  if (_tier1Cache !== null) return
  const db = await getDB()
  const row = await db.get('meta', 'stars_t1')
  _tier1Cache = row ? _parseT1Csv(row.value) : []
}

// --------------------------------------------------------------------------
// Public write helpers called by WelcomeScreen during data load
// --------------------------------------------------------------------------

export async function storeTier1Blob(csvText) {
  const db = await getDB()
  await db.put('meta', { key: 'stars_t1', value: csvText })
  _tier1Cache = null // invalidate cache so next query re-parses
}

export async function bulkPutZoneT2Blobs(items) {
  // items: Array<{zone: number, csv: string}>
  const db = await getDB()
  const hasNamed = db.objectStoreNames.contains('stars_named')
  const stores = hasNamed ? ['zones_t2', 'stars_named'] : ['zones_t2']
  const tx = db.transaction(stores, 'readwrite')
  const puts = items.map((item) => tx.objectStore('zones_t2').put(item))
  if (hasNamed) {
    const namedStars = items.flatMap((item) => _parseT2CsvNamedOnly(item.csv))
    namedStars.forEach((s) => puts.push(tx.objectStore('stars_named').put(s)))
  }
  await Promise.all(puts)
  await tx.done
}

// --------------------------------------------------------------------------
// Existing helpers (unchanged)
// --------------------------------------------------------------------------

export async function hasData() {
  const manifest = await getStoredManifest()
  if (!manifest) {
    const db = await getDB()
    const row = await db.get('meta', 'stars_t1')
    if (row) return true
    const count = await db.count('objects')
    return count > 0
  }
  const selectedMag = localStorage.getItem('selectedMag')
  const mag = selectedMag ? parseInt(selectedMag, 10) : null
  const activeSet = mag != null ? manifest.sets?.find((s) => s.mag === mag) : manifest.sets?.[0]
  if (!activeSet) return false
  const completed = await getCompletedChunks()
  return activeSet.t2_chunks.every((c) => completed.has(c.filename)) && !!(await getMeta('stars_t1'))
}

export async function clearAllStarAndObjectData() {
  const db = await getDB()
  const hasNamed = db.objectStoreNames.contains('stars_named')
  const stores = hasNamed ? ['zones_t2', 'objects', 'stars_named'] : ['zones_t2', 'objects']
  const tx = db.transaction(stores, 'readwrite')
  await tx.objectStore('zones_t2').clear()
  await tx.objectStore('objects').clear()
  if (hasNamed) await tx.objectStore('stars_named').clear()
  await tx.done
  await db.delete('meta', 'stars_t1')
  _tier1Cache = null
  await setMeta('completedChunks', [])
  await db.delete('meta', 'dataManifest')
}

export async function getMeta(key) {
  const db = await getDB()
  const row = await db.get('meta', key)
  return row ? row.value : undefined
}

export async function setMeta(key, value) {
  const db = await getDB()
  await db.put('meta', { key, value })
}

function _cloneSteps(steps) {
  if (!Array.isArray(steps)) return []
  return steps
    .map((step) => {
      if (!step || typeof step !== 'object') return null
      const startPoint = step.startPoint && typeof step.startPoint === 'object' ? { ...step.startPoint } : null
      const endPoint = step.endPoint && typeof step.endPoint === 'object' ? { ...step.endPoint } : null
      const multiplier = Number(step.multiplier)
      const out = {
        startPoint,
        endPoint,
        multiplier: Number.isFinite(multiplier) ? multiplier : 1,
      }
      if (step.final === true) out.final = true
      return out
    })
    .filter(Boolean)
}

export async function getObjectIdsWithFindingPaths() {
  const all = (await getMeta('findingPaths')) || {}
  return new Set(
    Object.entries(all)
      .filter(([, byStart]) => byStart && typeof byStart === 'object' && Object.keys(byStart).length > 0)
      .map(([id]) => id),
  )
}

export async function getFindingPathsForObject(objectId) {
  const all = (await getMeta('findingPaths')) || {}
  const byStart = all[objectId]
  if (!byStart || typeof byStart !== 'object') return {}
  const out = {}
  for (const [startHip, path] of Object.entries(byStart)) {
    out[startHip] = { steps: _cloneSteps(path?.steps) }
  }
  return out
}

export async function getAllFindingPaths() {
  return (await getMeta('findingPaths')) || {}
}

export async function replaceAllFindingPaths(data) {
  await setMeta('findingPaths', data && typeof data === 'object' ? data : {})
}

export async function saveFindingPathForObject(objectId, startHip, pathValue) {
  const all = (await getMeta('findingPaths')) || {}
  const key = String(startHip)
  const next = {
    ...all,
    [objectId]: {
      ...(all[objectId] || {}),
      [key]: { steps: _cloneSteps(pathValue?.steps) },
    },
  }
  await setMeta('findingPaths', next)
}

export async function deleteFindingPathForObject(objectId, startHip) {
  const all = (await getMeta('findingPaths')) || {}
  if (!all[objectId]) return
  const key = String(startHip)
  const byStart = { ...all[objectId] }
  delete byStart[key]
  const next = { ...all }
  if (Object.keys(byStart).length === 0) delete next[objectId]
  else next[objectId] = byStart
  await setMeta('findingPaths', next)
}

export async function incrementFindingPathsChanges() {
  const cur = await getMeta('findingPathsChanges')
  await setMeta('findingPathsChanges', (Number.isFinite(Number(cur)) ? Number(cur) : 0) + 1)
}

export async function getFindingPathsChanges() {
  const raw = await getMeta('findingPathsChanges')
  if (raw == null) return null
  return Number.isFinite(Number(raw)) ? Number(raw) : 0
}

export async function clearFindingPathsChanges() {
  await setMeta('findingPathsChanges', 0)
}

export async function storeManifest(manifest, chosenMag) {
  const stored = {
    sets: manifest.sets.map((set) => ({
      mag: set.mag,
      total_size: set.total_size,
      stars_t1: { filename: set.stars_t1.filename, hash: set.stars_t1.hash, size: set.stars_t1.size },
      objects: { filename: set.objects.filename, hash: set.objects.hash, size: set.objects.size },
      t2_chunks: set.t2_chunks.map(({ filename, hash, size, zones }) => ({ filename, hash, size, zones })),
    })),
  }
  await setMeta('dataManifest', stored)
  const activeSet = (chosenMag != null ? manifest.sets?.find((s) => s.mag === chosenMag) : null) ?? manifest.sets?.[0]
  if (activeSet?.stats) {
    await setMeta('catalogueStats', activeSet.stats)
  }
}

export async function getStoredManifest() {
  return getMeta('dataManifest')
}

export async function getCompletedChunks() {
  const arr = await getMeta('completedChunks')
  return new Set(arr || [])
}

export async function markChunkComplete(filename) {
  const arr = (await getMeta('completedChunks')) || []
  if (!arr.includes(filename)) {
    arr.push(filename)
    await setMeta('completedChunks', arr)
  }
}

export async function clearCompletedChunks(filenames) {
  if (!Array.isArray(filenames) || filenames.length === 0) {
    await setMeta('completedChunks', [])
    return
  }
  const arr = (await getMeta('completedChunks')) || []
  const removeSet = new Set(filenames)
  await setMeta(
    'completedChunks',
    arr.filter((name) => !removeSet.has(name)),
  )
}

export async function bulkPutObjects(items) {
  const db = await getDB()
  const tx = db.transaction('objects', 'readwrite')
  await Promise.all(items.map((item) => tx.store.put(item)))
  await tx.done
  const counts = {}
  for (const item of items) {
    const key = item.type === 'dso' ? item.dsoType || 'unknown' : item.type
    counts[key] = (counts[key] || 0) + 1
  }
  await setMeta('catalogueObjectCounts', counts)
}

export async function getCatalogueCounts() {
  const db = await getDB()
  const [starStats, objCounts, solarSystem, imageCount] = await Promise.all([
    getMeta('catalogueStats'),
    getMeta('catalogueObjectCounts'),
    getMeta('solar_system'),
    db.count('images'),
  ])
  if (!starStats && !objCounts) return null
  const s = starStats || {}
  const o = objCounts || {}
  return {
    stars: (s.stars_t1 || 0) + (s.stars_t2 || 0),
    variableStars: (s.variable_t1 || 0) + (s.variable_t2 || 0),
    doubleStars: (s.double_t1 || 0) + (o.double_star || 0),
    galaxies: (o.galaxy || 0) + (o['elliptical galaxy'] || 0) + (o['spiral galaxy'] || 0),
    openClusters: o['open cluster'] || 0,
    globularClusters: o['globular cluster'] || 0,
    planetaryNebulae: o['planetary nebula'] || 0,
    nebulae: (o['emission nebula'] || 0) + (o['reflection nebula'] || 0) + (o['dark nebula'] || 0),
    dsoImages: imageCount || 0,
    asteroids: solarSystem?.minor_planets?.length || 0,
  }
}

const _encoder = new TextEncoder()

function _roughBytes(value) {
  if (value == null) return 0
  if (value instanceof Blob) return value.size
  if (typeof value === 'string') return _encoder.encode(value).length
  if (value instanceof ArrayBuffer) return value.byteLength
  if (ArrayBuffer.isView(value)) return value.byteLength
  try {
    return _encoder.encode(JSON.stringify(value)).length
  } catch {
    return 0
  }
}

async function _storeBytes(db, storeName) {
  const rows = await db.getAll(storeName)
  let total = 0
  for (const row of rows) total += _roughBytes(row)
  return total
}

function _observationStats(observations) {
  const allObjects = []
  for (const obs of observations || []) {
    const entries = Array.isArray(obs?.objects) ? obs.objects : []
    for (const entry of entries) {
      const id = String(entry?.id || '').trim()
      if (id) allObjects.push(id)
    }
  }
  return {
    observationsCount: (observations || []).length,
    observedObjectsCount: allObjects.length,
    uniqueObservedObjectsCount: new Set(allObjects).size,
  }
}

function _countFindingPaths(findingPaths) {
  if (!findingPaths || typeof findingPaths !== 'object') return 0
  let count = 0
  for (const byStart of Object.values(findingPaths)) {
    if (!byStart || typeof byStart !== 'object') continue
    count += Object.keys(byStart).length
  }
  return count
}

function _countDsosFromMeta(objCounts) {
  if (!objCounts || typeof objCounts !== 'object') return null
  let total = 0
  for (const [key, value] of Object.entries(objCounts)) {
    if (key === 'double_star') continue
    total += Number(value) || 0
  }
  return total
}

export async function getAboutStats() {
  const db = await getDB()
  const [observations, starStats, objCounts, findingPaths, manifest] = await Promise.all([
    db.getAll('observations'),
    getMeta('catalogueStats'),
    getMeta('catalogueObjectCounts'),
    getMeta('findingPaths'),
    getMeta('dataManifest'),
  ])

  const [imagesBytes, observationsBytes] = await Promise.all([
    _storeBytes(db, 'images'),
    _storeBytes(db, 'observations'),
  ])

  const findingPathsBytes = _roughBytes(findingPaths)

  const selectedMag = Number(localStorage.getItem('selectedMag')) || null
  const activeSet =
    (selectedMag != null ? manifest?.sets?.find((s) => s.mag === selectedMag) : null) ?? manifest?.sets?.[0]
  const objectDataBytes = activeSet?.total_size ?? null

  const starsCount =
    (Number(starStats?.stars_t1) || 0) +
    (Number(starStats?.stars_t2) || 0) +
    (Number(starStats?.variable_t1) || 0) +
    (Number(starStats?.variable_t2) || 0)
  const dsoCount = _countDsosFromMeta(objCounts)

  return {
    objectDataBytes,
    imagesBytes,
    userDataBytes: observationsBytes + findingPathsBytes,
    starsCount,
    dsoCount,
    findingPathsCount: _countFindingPaths(findingPaths),
    ..._observationStats(observations),
  }
}

export async function bulkPutImages(items) {
  const db = await getDB()
  const tx = db.transaction('images', 'readwrite')
  await Promise.all(items.map((item) => tx.store.put(item)))
  await tx.done
}

export async function getImagesCount() {
  const db = await getDB()
  return db.count('images')
}

export async function bulkPutObservations(items) {
  const db = await getDB()
  const tx = db.transaction('observations', 'readwrite')
  await Promise.all(items.map((item) => tx.store.put(item)))
  await tx.done
}

export async function replaceAllObservations(items) {
  const db = await getDB()
  const tx = db.transaction('observations', 'readwrite')
  await tx.store.clear()
  if (Array.isArray(items) && items.length > 0) {
    await Promise.all(items.map((item) => tx.store.put(item)))
  }
  await tx.done
}

export async function getAllObservations() {
  const db = await getDB()
  return db.getAll('observations')
}

// --------------------------------------------------------------------------
// Zone helpers
// --------------------------------------------------------------------------

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

// --------------------------------------------------------------------------
// Main query
// --------------------------------------------------------------------------

// Return all sky objects whose position overlaps the equatorial bounding box.
// ra_min/ra_max and dec_min/dec_max in degrees.
// mag_limit caps which stars are returned; defaults to include all.
export async function getObjectsInArea(ra_min, ra_max, dec_min, dec_max, mag_limit = 99) {
  await _ensureTier1Loaded()

  // 1. Filter Tier-1 in-memory array by bounding box + mag_limit.
  const span = ra_max - ra_min
  const ra0n = ((ra_min % 360) + 360) % 360
  const ra1n = ((ra_max % 360) + 360) % 360
  const wraps = ra0n > ra1n

  function _inRA(ra) {
    if (span >= 360) return true // full-sky RA span; accept all
    return wraps ? ra >= ra0n || ra <= ra1n : ra >= ra0n && ra <= ra1n
  }
  const results = []
  for (const s of _tier1Cache) {
    const m = typeof s.mag === 'number' ? s.mag : s.mag[0]
    if (m > mag_limit) break // T1 is sorted by mag ascending; early exit
    const [ra, dec] = s.pos
    if (dec < dec_min || dec > dec_max) continue
    if (!_inRA(ra)) continue
    results.push(s)
  }

  // 2. Fetch Tier-2 zone blobs when FOV is narrow enough to need faint stars.
  if (mag_limit > T1_MAG_LIMIT) {
    const db = await getDB()
    const zones = _zonesForArea(ra_min, ra_max, dec_min, dec_max)
    const blobs = await Promise.all(zones.map((z) => db.get('zones_t2', z)))
    for (const blob of blobs) {
      if (!blob) continue
      const t2Stars = _parseT2Csv(blob.csv)
      for (const s of t2Stars) {
        const m = typeof s.mag === 'number' ? s.mag : s.mag[0]
        if (m > mag_limit) break // T2 per-zone blobs are sorted by mag ascending
        const [ra, dec] = s.pos
        if (dec < dec_min || dec > dec_max) continue
        if (!_inRA(ra)) continue
        results.push(s)
      }
    }
  }

  // 3. Query objects store for DSOs and double stars (existing logic).
  const dc_min = Math.max(0, Math.floor((Math.max(-90, dec_min) + 90) / DEC_BUCKET))
  const dc_max = Math.min(ZONE_DEC_CELLS - 1, Math.floor((Math.min(90, dec_max) + 90) / DEC_BUCKET))
  const rc_min = Math.floor(ra0n / RA_BUCKET)
  const rc_max = Math.floor(ra1n / RA_BUCKET)

  const db = await getDB()
  const tx = db.transaction('objects', 'readonly')
  const idx = tx.store.index('by_zone')
  const queries = []
  for (let dc = dc_min; dc <= dc_max; dc++) {
    const base = dc * ZONE_RA_CELLS
    if (span >= 360) {
      queries.push(idx.getAll(IDBKeyRange.bound(base, base + ZONE_RA_CELLS - 1)))
    } else if (rc_min <= rc_max) {
      queries.push(idx.getAll(IDBKeyRange.bound(base + rc_min, base + rc_max)))
    } else {
      queries.push(idx.getAll(IDBKeyRange.bound(base + rc_min, base + ZONE_RA_CELLS - 1)))
      queries.push(idx.getAll(IDBKeyRange.bound(base, base + rc_max)))
    }
  }
  const dsoArrays = await Promise.all(queries)
  for (const arr of dsoArrays) {
    for (const obj of arr) results.push(obj)
  }

  return results
}

// --------------------------------------------------------------------------
// Search index
// --------------------------------------------------------------------------

// Returns T1 stars, DSOs/double-stars, and named T2 stars (those with HIP/HD).
// Used by SearchPanel to build its index.
export async function getSearchIndex() {
  await _ensureTier1Loaded()
  const db = await getDB()
  const [stored, namedT2] = await Promise.all([
    db.getAll('objects'),
    db.objectStoreNames.contains('stars_named') ? db.getAll('stars_named') : Promise.resolve([]),
  ])
  const all = [..._tier1Cache, ...stored, ...namedT2]
  return all.map((obj) => {
    const aliases = SEARCH_ALIASES[obj.id]
    return aliases ? { ...obj, aliases } : obj
  })
}

export async function getTodayObservation() {
  const db = await getDB()
  const today = new Date().toISOString().slice(0, 10)
  return db.get('observations', today)
}

export async function getObservationByDate(date) {
  const db = await getDB()
  return db.get('observations', date)
}

export async function putObservation(record) {
  const db = await getDB()
  await db.put('observations', record)
}

export async function deleteObservationByDate(date) {
  const db = await getDB()
  await db.delete('observations', date)
}

export async function getPendingChangesCount() {
  const n = await getMeta('pendingChanges')
  return Number.isFinite(Number(n)) ? Number(n) : 0
}

export async function setPendingChangesCount(value = 0) {
  const next = Math.max(0, Number(value) || 0)
  await setMeta('pendingChanges', next)
  return next
}

export async function getPendingObservationDates() {
  const arr = await getMeta('pendingObservationDates')
  if (!Array.isArray(arr)) return []
  return [...new Set(arr.map((x) => String(x || '').trim()).filter(Boolean))].sort((a, b) => b.localeCompare(a))
}

export async function markPendingObservationDates(dates) {
  if (!Array.isArray(dates) || dates.length === 0) return
  const existing = await getPendingObservationDates()
  const merged = new Set(existing)
  for (const d of dates) {
    const v = String(d || '').trim()
    if (v) merged.add(v)
  }
  await setMeta(
    'pendingObservationDates',
    [...merged].sort((a, b) => b.localeCompare(a)),
  )
}

export async function clearPendingObservationDates() {
  await setMeta('pendingObservationDates', [])
}

export async function incrementPendingChanges(delta = 1, dates = []) {
  const next = (await getPendingChangesCount()) + delta
  await setMeta('pendingChanges', next)
  if (Array.isArray(dates) && dates.length > 0) {
    await markPendingObservationDates(dates)
  }
  return next
}

export async function toggleObjectObserved(objectId) {
  const db = await getDB()
  const today = new Date().toISOString().slice(0, 10)
  const existing = (await db.get('observations', today)) || { date: today, objects: [] }
  const idx = existing.objects.findIndex((o) => o.id === objectId)
  if (idx === -1) {
    existing.objects.push({ id: objectId })
  } else {
    existing.objects.splice(idx, 1)
  }
  await db.put('observations', existing)
  await incrementPendingChanges(1, [today])
  return existing.objects.some((o) => o.id === objectId)
}

export async function getObjectImage(objectId) {
  const db = await getDB()
  let catalogueId = objectId
  if (objectId?.startsWith('dso_')) {
    const raw = objectId.slice(4) // strip 'dso_' prefix
    if (raw.startsWith('M')) {
      // M-catalogue object IDs zero-pad to 3 digits (dso_M057 → M57)
      catalogueId = 'M' + parseInt(raw.slice(1), 10)
    } else {
      // NGC, IC, Caldwell etc. — filename matches the suffix directly
      catalogueId = raw
    }
  } else if (objectId?.startsWith('solar_')) {
    // solar_mercury → planet_mercury; solar_asteroid_vesta → planet_asteroid_vesta
    const solarKey = objectId
      .slice(6)
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
    catalogueId = 'planet_' + solarKey
    const exact = await db.get('images', catalogueId)
    if (exact) return exact
    if (catalogueId.startsWith('planet_asteroid_')) {
      return db.get('images', 'planet_asteroid')
    }
    return null
  }
  return db.get('images', catalogueId)
}

export async function getDoubleStarNear(ra_deg, dec_deg, radiusDeg = 0.5) {
  const db = await getDB()
  const zones = _zonesForArea(ra_deg - radiusDeg, ra_deg + radiusDeg, dec_deg - radiusDeg, dec_deg + radiusDeg)
  const tx = db.transaction('objects', 'readonly')
  const idx = tx.store.index('by_zone')
  let best = null
  let bestDist = Infinity
  for (const zone of zones) {
    const objs = await idx.getAll(IDBKeyRange.only(zone))
    for (const obj of objs) {
      if (obj.type !== 'double_star' || !obj.pos) continue
      const dra = Math.abs(obj.pos[0] - ra_deg)
      const ddec = Math.abs(obj.pos[1] - dec_deg)
      const dist = Math.sqrt(dra * dra + ddec * ddec)
      if (dist < radiusDeg && dist < bestDist) {
        bestDist = dist
        best = obj
      }
    }
  }
  return best
}
