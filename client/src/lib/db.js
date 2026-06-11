import { openDB as idbOpenDB } from 'idb'

const DB_NAME = 'observarium'
const DB_VERSION = 2

const RA_BUCKET = 5
const DEC_BUCKET = 5
export const ZONE_RA_CELLS = 72   // 360 / RA_BUCKET
export const ZONE_DEC_CELLS = 36  // 180 / DEC_BUCKET

// Compute sky-zone integer (0–2591) from equatorial coordinates.
// Zone ordering: dec_cell * ZONE_RA_CELLS + ra_cell — within each Dec band,
// RA cells are contiguous, enabling efficient IDB range queries per band.
export function computeZone(ra_deg, dec_deg) {
  const ra_cell = Math.floor(ra_deg / RA_BUCKET) % ZONE_RA_CELLS
  const dec_cell = Math.min(ZONE_DEC_CELLS - 1, Math.floor((dec_deg + 90) / DEC_BUCKET))
  return dec_cell * ZONE_RA_CELLS + ra_cell
}

let _db = null

async function getDB() {
  if (_db) return _db
  _db = await idbOpenDB(DB_NAME, DB_VERSION, {
    upgrade(db, oldVersion, newVersion, transaction) {
      if (oldVersion < 1) {
        db.createObjectStore('objects', { keyPath: 'id' })
        db.createObjectStore('images', { keyPath: 'catalogueId' })
        db.createObjectStore('observations', { keyPath: 'date' })
        db.createObjectStore('meta', { keyPath: 'key' })
      }
      if (oldVersion < 2) {
        transaction.objectStore('objects').createIndex('by_zone', 'zone')
      }
    }
  })
  return _db
}

export async function hasData() {
  const db = await getDB()
  const count = await db.count('objects')
  return count > 0
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

export async function bulkPutObjects(items) {
  const db = await getDB()
  const tx = db.transaction('objects', 'readwrite')
  await Promise.all(items.map(item => tx.store.put(item)))
  await tx.done
}

export async function bulkPutImages(items) {
  const db = await getDB()
  const tx = db.transaction('images', 'readwrite')
  await Promise.all(items.map(item => tx.store.put(item)))
  await tx.done
}

export async function bulkPutObservations(items) {
  const db = await getDB()
  const tx = db.transaction('observations', 'readwrite')
  await Promise.all(items.map(item => tx.store.put(item)))
  await tx.done
}

// Return all objects whose sky zone overlaps the given equatorial bounding box.
// ra_min/ra_max in degrees, dec_min/dec_max in degrees [-90, 90].
// Handles RA wrap-around (ra_min > ra_max after normalisation) and full circle.
export async function getObjectsInArea(ra_min, ra_max, dec_min, dec_max) {
  const dc_min = Math.max(0, Math.floor((Math.max(-90, dec_min) + 90) / DEC_BUCKET))
  const dc_max = Math.min(ZONE_DEC_CELLS - 1, Math.floor((Math.min(90, dec_max) + 90) / DEC_BUCKET))
  const span = ra_max - ra_min
  const ra0 = ((ra_min % 360) + 360) % 360
  const ra1 = ((ra_max % 360) + 360) % 360
  const rc_min = Math.floor(ra0 / RA_BUCKET)
  const rc_max = Math.floor(ra1 / RA_BUCKET)

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
      // RA wraps around 0/360
      queries.push(idx.getAll(IDBKeyRange.bound(base + rc_min, base + ZONE_RA_CELLS - 1)))
      queries.push(idx.getAll(IDBKeyRange.bound(base, base + rc_max)))
    }
  }

  const arrays = await Promise.all(queries)
  return arrays.flat()
}
