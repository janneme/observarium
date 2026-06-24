import JSZip from 'jszip'
import { getDataHash, getImagesHash, getManifest, getImagesUrl, getObservations } from './api.js'
import {
  bulkPutObjects,
  bulkPutImages,
  bulkPutObservations,
  setMeta,
  computeZone,
  storeTier1Blob,
  bulkPutZoneT2Blobs,
  getMeta,
  getImagesCount,
  storeManifest,
  getStoredManifest,
  getCompletedChunks,
  markChunkComplete,
  clearCompletedChunks,
} from './db.js'

async function fetchWithProgress(url, onProgress) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Fetch failed: ${res.status}`)
  const contentLength = res.headers.get('Content-Length')
  const total = contentLength ? parseInt(contentLength, 10) : 0
  const reader = res.body.getReader()
  const chunks = []
  let received = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    received += value.length
    if (total > 0) onProgress(received / total)
  }
  const merged = new Uint8Array(received)
  let offset = 0
  for (const chunk of chunks) {
    merged.set(chunk, offset)
    offset += chunk.length
  }
  return merged
}

export function objectIdFromDso(dso) {
  if (dso.m) return `dso_M${String(dso.m).padStart(3, '0')}`
  if (dso.ngc) return `dso_NGC${dso.ngc}`
  if (dso.ic) return `dso_IC${dso.ic}`
  return null
}

export function parseObjects(objectsJson) {
  const items = []
  for (const [key, value] of Object.entries(objectsJson)) {
    if (key.startsWith('stars')) continue
    if (key === 'dso') {
      for (const [constellation, dsos] of Object.entries(value)) {
        for (const dso of dsos) {
          const id = objectIdFromDso(dso)
          if (id) {
            const ra_deg = dso.pos[0] * 15
            items.push({
              constellation,
              ...dso,
              pos: [ra_deg, dso.pos[1]],
              id,
              type: 'dso',
              dsoType: dso.type,
              zone: computeZone(ra_deg, dso.pos[1]),
            })
          }
        }
      }
    } else if (key.startsWith('double_stars')) {
      for (const [wdsId, ds] of Object.entries(value)) {
        const ra_deg = ds.pos[0] * 15
        items.push({
          ...ds,
          pos: [ra_deg, ds.pos[1]],
          id: `double_WDS${wdsId}`,
          type: 'double_star',
          zone: computeZone(ra_deg, ds.pos[1]),
        })
      }
    }
  }
  return items
}

function extractMetaKeys(objectsJson) {
  const meta = {}
  for (const key of ['constellations', 'solar_system', 'moon_features']) {
    if (objectsJson[key] !== undefined) meta[key] = objectsJson[key]
  }
  return meta
}

async function downloadZip(url, onProgress) {
  const data = await fetchWithProgress(url, onProgress || (() => {}))
  return JSZip.loadAsync(data)
}

async function ingestT1(url) {
  const zip = await downloadZip(url)
  const file = zip.file('stars_t1.csv')
  if (!file) throw new Error('stars_t1.csv not found in stars_t1.zip')
  await storeTier1Blob(await file.async('string'))
}

async function ingestObjects(url) {
  const zip = await downloadZip(url)
  const file = zip.file('objects.json')
  if (!file) throw new Error('objects.json not found in objects.zip')
  const objectsJson = JSON.parse(await file.async('string'))
  await bulkPutObjects(parseObjects(objectsJson))
  for (const [k, v] of Object.entries(extractMetaKeys(objectsJson))) await setMeta(k, v)
}

async function ingestChunk(url, filename, onProgress) {
  const zip = await downloadZip(url, onProgress)
  for (const [entryName, file] of Object.entries(zip.files)) {
    if (file.dir || !entryName.endsWith('.csv')) continue
    const zone = parseInt(entryName.replace('.csv', ''), 10)
    if (isNaN(zone)) continue
    await bulkPutZoneT2Blobs([{ zone, csv: await file.async('string') }])
  }
  await markChunkComplete(filename)
}

function getChangedChunkFilenames(manifest, storedManifest) {
  if (!storedManifest || !Array.isArray(storedManifest.t2_chunks)) {
    return manifest.t2_chunks.map((chunk) => chunk.filename)
  }
  const oldByName = new Map(storedManifest.t2_chunks.map((chunk) => [chunk.filename, chunk.hash]))
  return manifest.t2_chunks
    .filter((chunk) => oldByName.get(chunk.filename) !== chunk.hash)
    .map((chunk) => chunk.filename)
}

async function downloadAndStoreImages(onImagesProgress) {
  const imgProg = onImagesProgress || (() => {})
  const imagesUrl = await getImagesUrl()
  const imagesData = await fetchWithProgress(imagesUrl, (p) => imgProg(p * 0.7))
  const imagesZip = await JSZip.loadAsync(imagesData, {
    onUpdate(metadata) {
      if (metadata.percent != null) imgProg(0.7 + (metadata.percent / 100) * 0.3)
    },
  })
  const imageItems = []
  for (const [filename, file] of Object.entries(imagesZip.files)) {
    if (file.dir) continue
    const ext = filename.split('.').pop().toLowerCase()
    const catalogueId = filename.replace(/\.[^.]+$/, '')
    const blob = await file.async('blob')
    const mimeType =
      ext === 'png' ? 'image/png' : ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg' : 'application/octet-stream'
    imageItems.push({ catalogueId, blob: new Blob([blob], { type: mimeType }), filename })
  }
  const imagesSize = imageItems.reduce((s, item) => s + item.blob.size, 0)
  await bulkPutImages(imageItems)
  imgProg(1)
  return imagesSize
}

async function maybeRefreshImages(onImagesProgress) {
  const [remoteImagesHash, localImagesHash] = await Promise.all([getImagesHash(), getMeta('imagesHash')])
  if (remoteImagesHash && localImagesHash && remoteImagesHash === localImagesHash) {
    const imgProg = onImagesProgress || (() => {})
    imgProg(1)
    return { imagesSize: 0, imagesChanged: false, remoteImagesHash }
  }
  const imagesSize = await downloadAndStoreImages(onImagesProgress)
  if (remoteImagesHash) await setMeta('imagesHash', remoteImagesHash)
  return { imagesSize, imagesChanged: true, remoteImagesHash }
}

/**
 * Run the full data sync: objects (T1 + T2), images, observations.
 *
 * Callbacks (all optional):
 *   onObjectsProgress(fraction)  — 0..1 as objects download
 *   onImagesProgress(fraction)   — 0..1 as images download
 *   onObservationsDone()         — fired when observations are stored
 *
 * Returns { objectsSize, imagesSize, observationsSize } in bytes.
 */
export async function runSync({ onObjectsProgress, onImagesProgress, onObservationsDone } = {}) {
  const objProg = onObjectsProgress || (() => {})
  const imgProg = onImagesProgress || (() => {})
  const obsDone = onObservationsDone || (() => {})

  await clearCompletedChunks()

  // Objects
  const manifest = await getManifest()
  const completedChunks = await getCompletedChunks()
  const pendingChunks = manifest.t2_chunks.filter((c) => !completedChunks.has(c.filename))
  const t2Total = pendingChunks.reduce((s, c) => s + c.size, 0)
  const totalBytes = manifest.stars_t1.size + manifest.objects.size + t2Total
  let bytesLoaded = 0

  await ingestT1(manifest.stars_t1.url)
  bytesLoaded += manifest.stars_t1.size
  objProg(bytesLoaded / totalBytes)

  await ingestObjects(manifest.objects.url)
  bytesLoaded += manifest.objects.size
  objProg(bytesLoaded / totalBytes)

  for (const chunk of manifest.t2_chunks) {
    if (completedChunks.has(chunk.filename)) continue
    await ingestChunk(chunk.url, chunk.filename, (p) => objProg((bytesLoaded + chunk.size * p) / totalBytes))
    bytesLoaded += chunk.size
    objProg(bytesLoaded / totalBytes)
  }

  await storeManifest(manifest)
  if (manifest.version) await setMeta('dataHash', manifest.version)
  objProg(1)

  // Images
  const { imagesSize } = await maybeRefreshImages(imgProg)

  // Observations
  const observations = await getObservations()
  const observationsSize = JSON.stringify(observations).length
  if (Array.isArray(observations) && observations.length > 0) {
    await bulkPutObservations(observations)
  }
  obsDone()

  return { objectsSize: totalBytes, imagesSize, observationsSize }
}

/**
 * Incremental data update for the "Update Data" screen.
 *
 * Behaviour:
 * - Checks /data-hash and exits quickly when local data are up to date.
 * - If changed, downloads only changed object artifacts (stars_t1, objects, changed t2 chunks).
 * - Refreshes images only when object-data hash changed.
 * - Does not overwrite observations during update-data flow.
 */
export async function runUpdateSync({ onObjectsProgress, onImagesProgress, onObservationsDone } = {}) {
  const objProg = onObjectsProgress || (() => {})
  const imgProg = onImagesProgress || (() => {})
  const obsDone = onObservationsDone || (() => {})

  const [remoteDataHash, remoteImagesHash, storedManifest, localImagesHash, localImagesCount] = await Promise.all([
    getDataHash(),
    getImagesHash(),
    getStoredManifest(),
    getMeta('imagesHash'),
    getImagesCount(),
  ])
  const dataUpToDate = !!(storedManifest?.version && storedManifest.version === remoteDataHash)
  const hasLocalImages = localImagesCount > 0
  const imagesUpToDate = !!(
    remoteImagesHash &&
    ((localImagesHash && remoteImagesHash === localImagesHash) || (!localImagesHash && hasLocalImages))
  )

  if (imagesUpToDate && remoteImagesHash && localImagesHash !== remoteImagesHash) {
    await setMeta('imagesHash', remoteImagesHash)
  }

  if (dataUpToDate && imagesUpToDate) {
    return {
      objectsSize: 0,
      imagesSize: 0,
      observationsSize: 0,
      objectsUpToDate: true,
      imagesUpToDate: true,
      upToDate: true,
    }
  }

  let manifest = storedManifest
  if (!dataUpToDate) manifest = await getManifest()
  if (!manifest) throw new Error('Missing local manifest for update check')

  const starsChanged = !storedManifest || storedManifest.stars_t1?.hash !== manifest.stars_t1.hash
  const objectsZipChanged = !storedManifest || storedManifest.objects?.hash !== manifest.objects.hash
  const changedChunkFilenames = getChangedChunkFilenames(manifest, storedManifest)
  const changedChunkSet = new Set(changedChunkFilenames)
  const changedChunks = manifest.t2_chunks.filter((chunk) => changedChunkSet.has(chunk.filename))
  const objectDataChanged = starsChanged || objectsZipChanged || changedChunks.length > 0

  if (!objectDataChanged && imagesUpToDate) {
    if (!dataUpToDate && remoteDataHash) await setMeta('dataHash', remoteDataHash)
    return {
      objectsSize: 0,
      imagesSize: 0,
      observationsSize: 0,
      objectsUpToDate: true,
      imagesUpToDate: true,
      upToDate: true,
    }
  }

  objProg(0)
  imgProg(0)

  if (changedChunkFilenames.length > 0) {
    await clearCompletedChunks(changedChunkFilenames)
  }

  const totalBytes =
    (starsChanged ? manifest.stars_t1.size : 0) +
    (objectsZipChanged ? manifest.objects.size : 0) +
    changedChunks.reduce((s, chunk) => s + chunk.size, 0)

  let bytesLoaded = 0
  if (totalBytes === 0) {
    objProg(1)
  } else {
    if (starsChanged) {
      await ingestT1(manifest.stars_t1.url)
      bytesLoaded += manifest.stars_t1.size
      objProg(bytesLoaded / totalBytes)
    }
    if (objectsZipChanged) {
      await ingestObjects(manifest.objects.url)
      bytesLoaded += manifest.objects.size
      objProg(bytesLoaded / totalBytes)
    }
    for (const chunk of changedChunks) {
      await ingestChunk(chunk.url, chunk.filename, (p) => objProg((bytesLoaded + chunk.size * p) / totalBytes))
      bytesLoaded += chunk.size
      objProg(bytesLoaded / totalBytes)
    }
  }

  if (!dataUpToDate) {
    await storeManifest(manifest)
    if (remoteDataHash) await setMeta('dataHash', remoteDataHash)
  }
  objProg(1)

  let imagesSize = 0
  if (imagesUpToDate) {
    imgProg(1)
  } else {
    const result = await downloadAndStoreImages(imgProg)
    imagesSize = result
    if (remoteImagesHash) await setMeta('imagesHash', remoteImagesHash)
  }
  obsDone()
  return {
    objectsSize: totalBytes,
    imagesSize,
    observationsSize: 0,
    objectsUpToDate: !objectDataChanged,
    imagesUpToDate,
    upToDate: false,
  }
}
