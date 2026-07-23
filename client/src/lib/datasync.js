import {
  getDataHash,
  getImagesHash,
  getManifest,
  getImagesUrl,
  getObservations,
  getFindingPaths,
  getTelescopes,
  getEyepieces,
} from './api.js'
import {
  bulkPutObjects,
  bulkPutImages,
  bulkPutObservations,
  replaceAllFindingPaths,
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
  clearAllStarAndObjectData,
} from './db.js'

// Pulling the user's previously-synced data (observations, finding paths,
// telescopes, eyepieces) down during the first-time catalogue download is
// convenient for normal use (a new install picks up where you left off) but
// gets in the way when testing the sync feature itself, which wants to
// start from a genuinely empty profile. Defaults to on; set to the literal
// string "false" in client/.env.development to disable for local testing.
const LOAD_USER_DATA_ON_INIT = import.meta.env.VITE_LOAD_USER_DATA_ON_INIT !== 'false'

// JSZip is only ever needed for this catalogue/image download flow, not for
// normal app startup — loaded on demand (and cached) so it lands in its own
// chunk instead of bloating the main bundle.
let _jsZipPromise = null
function getJSZip() {
  if (!_jsZipPromise) _jsZipPromise = import('jszip').then((m) => m.default)
  return _jsZipPromise
}

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
  if (dso.cald) return `dso_C${dso.cald}`
  if (dso.name) return `dso_${dso.name.replace(/\s+/g, '_')}`
  const [ra, dec] = dso.pos
  return `dso_POS_${Math.round(ra * 1000)}_${Math.round(dec * 1000)}`
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
  const [data, JSZip] = await Promise.all([fetchWithProgress(url, onProgress || (() => {})), getJSZip()])
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

function getChangedChunkFilenames(activeSet, storedSet) {
  if (!storedSet || !Array.isArray(storedSet.t2_chunks)) {
    return activeSet.t2_chunks.map((chunk) => chunk.filename)
  }
  const oldByName = new Map(storedSet.t2_chunks.map((chunk) => [chunk.filename, chunk.hash]))
  return activeSet.t2_chunks
    .filter((chunk) => oldByName.get(chunk.filename) !== chunk.hash)
    .map((chunk) => chunk.filename)
}

async function downloadAndStoreImages(onImagesProgress) {
  const imgProg = onImagesProgress || (() => {})
  const imagesUrl = await getImagesUrl()
  const imagesData = await fetchWithProgress(imagesUrl, (p) => imgProg(p * 0.7))
  const JSZip = await getJSZip()
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

// Pulls the user's previously-synced data (all four categories) down and
// seeds it into local storage. Only meant for a fresh/near-empty profile —
// this is a plain "put", not a merge, matching what the single-category
// version of this step always did for observations.
async function pullUserData() {
  const [observations, findingPaths, telescopes, eyepieces] = await Promise.all([
    getObservations(),
    getFindingPaths(),
    getTelescopes(),
    getEyepieces(),
  ])

  let size = 0
  if (Array.isArray(observations) && observations.length > 0) {
    await bulkPutObservations(observations)
    size += JSON.stringify(observations).length
  }
  if (findingPaths && typeof findingPaths === 'object' && Object.keys(findingPaths).length > 0) {
    await replaceAllFindingPaths(findingPaths)
    size += JSON.stringify(findingPaths).length
  }
  if (Array.isArray(telescopes) && telescopes.length > 0) {
    await setMeta('telescopes', telescopes)
    size += JSON.stringify(telescopes).length
  }
  if (Array.isArray(eyepieces) && eyepieces.length > 0) {
    await setMeta('eyepieces', eyepieces)
    size += JSON.stringify(eyepieces).length
  }
  return size
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
 * Run the full data sync: objects (T1 + T2), images, user data (observations,
 * finding paths, telescopes, eyepieces — gated by VITE_LOAD_USER_DATA_ON_INIT).
 *
 * Callbacks (all optional):
 *   onObjectsProgress(fraction)  — 0..1 as objects download
 *   onImagesProgress(fraction)   — 0..1 as images download
 *   onUserDataDone()             — fired when user data is stored (or skipped)
 *
 * Returns { objectsSize, imagesSize, userDataSize } in bytes.
 */
export async function runSync({ mag, onObjectsProgress, onImagesProgress, onUserDataDone } = {}) {
  const objProg = onObjectsProgress || (() => {})
  const imgProg = onImagesProgress || (() => {})
  const userDataDone = onUserDataDone || (() => {})

  await clearCompletedChunks()

  // Fetch manifest with URLs for the chosen magnitude set
  const manifest = await getManifest(mag)
  const activeSet = manifest.sets?.find((s) => s.mag === mag) ?? manifest.sets?.[0]
  if (!activeSet) throw new Error('No data set found in manifest')

  const completedChunks = await getCompletedChunks()
  const pendingChunks = activeSet.t2_chunks.filter((c) => !completedChunks.has(c.filename))
  const t2Total = pendingChunks.reduce((s, c) => s + c.size, 0)
  const totalBytes = activeSet.stars_t1.size + activeSet.objects.size + t2Total
  let bytesLoaded = 0

  await ingestT1(activeSet.stars_t1.url)
  bytesLoaded += activeSet.stars_t1.size
  objProg(bytesLoaded / totalBytes)

  await ingestObjects(activeSet.objects.url)
  bytesLoaded += activeSet.objects.size
  objProg(bytesLoaded / totalBytes)

  for (const chunk of activeSet.t2_chunks) {
    if (completedChunks.has(chunk.filename)) continue
    await ingestChunk(chunk.url, chunk.filename, (p) => objProg((bytesLoaded + chunk.size * p) / totalBytes))
    bytesLoaded += chunk.size
    objProg(bytesLoaded / totalBytes)
  }

  await storeManifest(manifest, mag)
  const remoteDataHash = await getDataHash()
  if (remoteDataHash) await setMeta('dataHash', remoteDataHash)
  await setMeta('syncDate', new Date().toISOString())
  objProg(1)

  // Images
  const { imagesSize } = await maybeRefreshImages(imgProg)

  // User data
  const userDataSize = LOAD_USER_DATA_ON_INIT ? await pullUserData() : 0
  userDataDone()

  return { objectsSize: totalBytes, imagesSize, userDataSize }
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
export async function runUpdateSync({ mag, onObjectsProgress, onImagesProgress, onObservationsDone } = {}) {
  const objProg = onObjectsProgress || (() => {})
  const imgProg = onImagesProgress || (() => {})
  const obsDone = onObservationsDone || (() => {})

  const [remoteDataHash, remoteImagesHash, storedManifest, localDataHash, localImagesHash, localImagesCount] =
    await Promise.all([
      getDataHash(),
      getImagesHash(),
      getStoredManifest(),
      getMeta('dataHash'),
      getMeta('imagesHash'),
      getImagesCount(),
    ])

  const storedSet = storedManifest?.sets?.find((s) => s.mag === mag) ?? storedManifest?.sets?.[0]
  const dataUpToDate = !!(localDataHash && localDataHash === remoteDataHash && storedSet != null)
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

  // Fetch manifest with URLs for the chosen magnitude set
  let manifest = null
  let activeSet = null
  if (!dataUpToDate) {
    manifest = await getManifest(mag)
    activeSet = manifest.sets?.find((s) => s.mag === mag) ?? manifest.sets?.[0]
  }
  if (!activeSet && storedSet) {
    // data is up-to-date, only images need refresh — use stored set for size tracking
    activeSet = storedSet
  }
  if (!activeSet) throw new Error('Missing manifest set for update check')

  const starsChanged = !storedSet || storedSet.stars_t1?.hash !== activeSet.stars_t1.hash
  const objectsZipChanged = !storedSet || storedSet.objects?.hash !== activeSet.objects.hash
  const changedChunkFilenames = getChangedChunkFilenames(activeSet, storedSet)
  const changedChunkSet = new Set(changedChunkFilenames)
  const changedChunks = activeSet.t2_chunks.filter((chunk) => changedChunkSet.has(chunk.filename))
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
    (starsChanged ? activeSet.stars_t1.size : 0) +
    (objectsZipChanged ? activeSet.objects.size : 0) +
    changedChunks.reduce((s, chunk) => s + chunk.size, 0)

  let bytesLoaded = 0
  if (totalBytes === 0) {
    objProg(1)
  } else {
    if (starsChanged) {
      await ingestT1(activeSet.stars_t1.url)
      bytesLoaded += activeSet.stars_t1.size
      objProg(bytesLoaded / totalBytes)
    }
    if (objectsZipChanged) {
      await ingestObjects(activeSet.objects.url)
      bytesLoaded += activeSet.objects.size
      objProg(bytesLoaded / totalBytes)
    }
    for (const chunk of changedChunks) {
      await ingestChunk(chunk.url, chunk.filename, (p) => objProg((bytesLoaded + chunk.size * p) / totalBytes))
      bytesLoaded += chunk.size
      objProg(bytesLoaded / totalBytes)
    }
  }

  if (!dataUpToDate && manifest) {
    await storeManifest(manifest, mag)
    if (remoteDataHash) await setMeta('dataHash', remoteDataHash)
  }
  await setMeta('syncDate', new Date().toISOString())
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

export { clearAllStarAndObjectData }
