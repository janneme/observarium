<script>
  import { push } from 'svelte-spa-router'
  import JSZip from 'jszip'
  import CustomInput from '../components/CustomInput.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import { login, getManifest, getImagesUrl, getObservations } from '../lib/api.js'
  import { bulkPutObjects, bulkPutImages, bulkPutObservations, setMeta, computeZone, storeTier1Blob, bulkPutZoneT2Blobs, storeManifest, getStoredManifest, getCompletedChunks, markChunkComplete } from '../lib/db.js'
  import { keyboardActive } from '../stores/keyboard.js'

  let username = ''
  let password = ''

  const appVersion = import.meta.env.VITE_APP_VERSION_DATE || 'dev'

  let hasToken = !!sessionStorage.getItem('token')

  let phase = 'idle'  // idle | loading | done | error
  let errorMsg = ''

  // Per-phase progress: each is 0..1
  let objectsProgress = 0
  let imagesProgress = 0
  let observationsDone = false

  let objectsSize = 0
  let imagesSize = 0
  let observationsSize = 0

  function formatSize(bytes) {
    if (bytes >= 1_000_000) return `${+(bytes / 1_000_000).toPrecision(2)} MB`
    if (bytes >= 1_000) return `${+(bytes / 1_000).toPrecision(2)} kB`
    return `${bytes} B`
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

  function objectIdFromStar(star) {
    if (star.hip) return `star_HIP${star.hip}`
    if (star.hd) return `star_HD${star.hd}`
    return null
  }

  function objectIdFromDso(dso) {
    if (dso.m) return `dso_M${String(dso.m).padStart(3, '0')}`
    if (dso.ngc) return `dso_NGC${dso.ngc}`
    if (dso.ic) return `dso_IC${dso.ic}`
    return null
  }

  async function downloadZip(url, onProgress) {
    const cb = onProgress || (() => {})
    const data = await fetchWithProgress(url, cb)
    return JSZip.loadAsync(data)
  }

  async function ingestT1(url) {
    const zip = await downloadZip(url)
    const file = zip.file('stars_t1.csv')
    if (!file) throw new Error('stars_t1.csv not found in stars_t1.zip')
    const text = await file.async('string')
    await storeTier1Blob(text)
  }

  async function ingestObjects(url) {
    const zip = await downloadZip(url)
    const file = zip.file('objects.json')
    if (!file) throw new Error('objects.json not found in objects.zip')
    const text = await file.async('string')
    const objectsJson = JSON.parse(text)
    const items = parseObjects(objectsJson)
    await bulkPutObjects(items)
    const metaKeys = extractMetaKeys(objectsJson)
    for (const [k, v] of Object.entries(metaKeys)) await setMeta(k, v)
  }

  async function ingestChunk(url, filename, onProgress) {
    const zip = await downloadZip(url, onProgress)
    for (const [entryName, file] of Object.entries(zip.files)) {
      if (file.dir || !entryName.endsWith('.csv')) continue
      const zone = parseInt(entryName.replace('.csv', ''), 10)
      if (isNaN(zone)) continue
      const csv = await file.async('string')
      await bulkPutZoneT2Blobs([{ zone, csv }])
    }
    await markChunkComplete(filename)
  }

  function parseObjects(objectsJson) {
    const items = []
    for (const [key, value] of Object.entries(objectsJson)) {
      if (key.startsWith('stars')) {
        // Stars are now delivered via CSV blobs; skip JSON star entries.
        continue
      } else if (key === 'dso') {
        for (const [constellation, dsos] of Object.entries(value)) {
          for (const dso of dsos) {
            const id = objectIdFromDso(dso)
            if (id) {
              const ra_deg = dso.pos[0] * 15
              items.push({ constellation, ...dso, pos: [ra_deg, dso.pos[1]], id, type: 'dso', dsoType: dso.type, zone: computeZone(ra_deg, dso.pos[1]) })
            }
          }
        }
      } else if (key.startsWith('double_stars')) {
        // value is {wds_id: {wds, disc, pos, pairs, ...}}
        for (const [wdsId, ds] of Object.entries(value)) {
          const ra_deg = ds.pos[0] * 15
          items.push({ ...ds, pos: [ra_deg, ds.pos[1]], id: `double_WDS${wdsId}`, type: 'double_star', zone: computeZone(ra_deg, ds.pos[1]) })
        }
      } else {
        // constellations, solar_system, moon_features → store in meta
        // (handled separately after this function)
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

  async function handleLoad() {
    if (!hasToken && (!username || !password)) {
      errorMsg = 'Enter username and password'
      return
    }
    phase = 'loading'
    errorMsg = ''
    objectsProgress = 0
    imagesProgress = 0
    observationsDone = false

    try {
      // Step 1 — authenticate (skip if we already have a token)
      if (!hasToken) {
        await login(username, password)
      }

      // Step 2 — objects (manifest-driven)
      const manifest = await getManifest()
      const completedChunks = await getCompletedChunks()
      const t2Total = manifest.t2_chunks
        .filter(c => !completedChunks.has(c.filename))
        .reduce((s, c) => s + c.size, 0)
      const totalBytes = manifest.stars_t1.size + manifest.objects.size + t2Total
      objectsSize = totalBytes
      let bytesLoaded = 0
      const onChunkProgress = (chunkSize) => (p) => {
        objectsProgress = (bytesLoaded + chunkSize * p) / totalBytes
      }
      await ingestT1(manifest.stars_t1.url)
      bytesLoaded += manifest.stars_t1.size
      objectsProgress = bytesLoaded / totalBytes
      await ingestObjects(manifest.objects.url)
      bytesLoaded += manifest.objects.size
      objectsProgress = bytesLoaded / totalBytes
      for (const chunk of manifest.t2_chunks) {
        if (completedChunks.has(chunk.filename)) continue
        await ingestChunk(chunk.url, chunk.filename, onChunkProgress(chunk.size))
        bytesLoaded += chunk.size
        objectsProgress = bytesLoaded / totalBytes
      }
      await storeManifest(manifest)
      objectsProgress = 1

      // Step 3 — images
      const imagesUrl = await getImagesUrl()
      const imagesData = await fetchWithProgress(imagesUrl, p => { imagesProgress = p * 0.7 })

      const imagesZip = await JSZip.loadAsync(imagesData, {
        onUpdate(metadata) {
          if (metadata.percent != null) imagesProgress = 0.7 + metadata.percent / 100 * 0.3
        }
      })

      const imageItems = []
      for (const [filename, file] of Object.entries(imagesZip.files)) {
        if (file.dir) continue
        const ext = filename.split('.').pop().toLowerCase()
        const catalogueId = filename.replace(/\.[^.]+$/, '')
        const blob = await file.async('blob')
        const mimeType = ext === 'png' ? 'image/png' : ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg' : 'application/octet-stream'
        imageItems.push({ catalogueId, blob: new Blob([blob], { type: mimeType }), filename })
      }
      imagesSize = imageItems.reduce((s, item) => s + item.blob.size, 0)
      await bulkPutImages(imageItems)
      imagesProgress = 1

      // Step 4 — observations
      const observations = await getObservations()
      observationsSize = JSON.stringify(observations).length
      if (Array.isArray(observations) && observations.length > 0) {
        await bulkPutObservations(observations)
      }
      observationsDone = true

      phase = 'done'
    } catch (err) {
      console.error('[WelcomeScreen] handleLoad failed:', err)
      phase = 'error'
      if (err.message && err.message.includes('401')) {
        hasToken = false
        sessionStorage.removeItem('token')
        errorMsg = 'Session expired. Please log in again.'
      } else {
        errorMsg = err.message || String(err)
      }
    }
  }

  async function handleContinue() {
    await push('/main')
  }
</script>

<div class="welcome-screen">
  <div class="welcome-card">
    <div class="app-title">Observarium</div>
    <div class="app-subtitle">Astronomy Field Notes</div>
    <div class="app-version">v{appVersion}</div>

    <p class="app-description">
      Mobile astronomy companion — identify sky objects, find them through the
      finder scope, track observations, and test your knowledge with quizzes.
    </p>

    {#if phase === 'idle' || phase === 'error'}
      <p class="welcome-text">
        Welcome. Load your observation data to get started.
      </p>

      <div class="form">
        {#if !hasToken}
          <label for="username-input">Username</label>
          <CustomInput id="username-input" bind:value={username} placeholder="username" />

          <label for="password-input">Password</label>
          <CustomInput id="password-input" bind:value={password} placeholder="password" mask={true} />
        {/if}

        {#if errorMsg}
          <div class="error-msg">{errorMsg}</div>
        {/if}
      </div>

      <button class="load-btn" on:click={handleLoad}>Load Application Data</button>
    {/if}

    {#if phase === 'loading' || phase === 'done'}
      <div class="phases">
        <div class="phase-row">
          <span class="phase-label">Objects</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {Math.round(objectsProgress * 100)}%"></div>
          </div>
          <span class="phase-pct">{Math.round(objectsProgress * 100)}%{phase === 'done' && objectsSize ? ` (${formatSize(objectsSize)})` : ''}</span>
        </div>

        <div class="phase-row">
          <span class="phase-label">Images</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {Math.round(imagesProgress * 100)}%"></div>
          </div>
          <span class="phase-pct">{Math.round(imagesProgress * 100)}%{phase === 'done' && imagesSize ? ` (${formatSize(imagesSize)})` : ''}</span>
        </div>

        <div class="phase-row">
          <span class="phase-label">Observations</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {observationsDone ? 100 : 0}%"></div>
          </div>
          <span class="phase-pct">{observationsDone ? '100' : '0'}%{phase === 'done' && observationsSize ? ` (${formatSize(observationsSize)})` : ''}</span>
        </div>
      </div>

      {#if phase === 'loading'}
        <div class="loading-hint">Loading…</div>
      {:else}
        <button class="load-btn" on:click={handleContinue}>Continue</button>
      {/if}
    {/if}
  </div>

  {#if $keyboardActive}
    <OnScreenKeyboard />
  {/if}
</div>

<style>
.welcome-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  height: 100vh;
  overflow: hidden;
  padding: 1rem;
  box-sizing: border-box;
}

.welcome-card {
  width: 100%;
  max-width: 420px;
  padding: 1.5rem;
  box-sizing: border-box;
}

.app-title {
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--fg);
}

.app-subtitle {
  font-size: 0.9rem;
  opacity: 0.6;
  margin-bottom: 0.25rem;
}

.app-version {
  font-size: 0.75rem;
  opacity: 0.4;
  margin-bottom: 1.25rem;
}

.app-description {
  font-size: 0.85rem;
  opacity: 0.65;
  line-height: 1.5;
  margin: 0 0 1.25rem;
}

.welcome-text {
  margin: 0 0 1.25rem;
  opacity: 0.75;
  font-size: 0.9rem;
  line-height: 1.5;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

label {
  font-size: 0.8rem;
  opacity: 0.7;
  margin-bottom: -0.25rem;
}

.error-msg {
  font-size: 0.85rem;
  color: var(--accent);
  padding: 0.25rem 0;
}

.load-btn {
  margin-top: 0.75rem;
  padding: 0.65rem 1rem;
  font-size: 1rem;
  cursor: pointer;
  border-radius: 6px;
  border: 1px solid rgba(127,127,127,0.25);
  background: none;
  color: var(--fg);
  transition: opacity 120ms ease;
}

.load-btn:hover {
  opacity: 0.8;
}

.phases {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.phase-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.phase-label {
  width: 90px;
  font-size: 0.85rem;
  opacity: 0.75;
  flex-shrink: 0;
}

.progress-track {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: rgba(127,127,127,0.15);
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 100ms linear;
}

.phase-pct {
  min-width: 36px;
  text-align: right;
  font-size: 0.8rem;
  opacity: 0.6;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.loading-hint {
  margin-top: 1rem;
  font-size: 0.85rem;
  opacity: 0.55;
}
</style>
