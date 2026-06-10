import { openDB as idbOpenDB } from 'idb'

const DB_NAME = 'observarium'
const DB_VERSION = 1

let _db = null

async function getDB() {
  if (_db) return _db
  _db = await idbOpenDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      db.createObjectStore('objects', { keyPath: 'id' })
      db.createObjectStore('images', { keyPath: 'catalogueId' })
      db.createObjectStore('observations', { keyPath: 'date' })
      db.createObjectStore('meta', { keyPath: 'key' })
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
