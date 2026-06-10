<script>
  import { push } from 'svelte-spa-router'
  import JSZip from 'jszip'
  import CustomInput from '../components/CustomInput.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import { login, getObjectsUrl, getImagesUrl, getObservations } from '../lib/api.js'
  import { bulkPutObjects, bulkPutImages, bulkPutObservations, setMeta } from '../lib/db.js'
  import { keyboardActive } from '../stores/keyboard.js'

  let username = ''
  let password = ''

  let phase = 'idle'  // idle | loading | done | error
  let errorMsg = ''

  // Per-phase progress: each is 0..1
  let objectsProgress = 0
  let imagesProgress = 0
  let observationsDone = false

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

  function parseObjects(objectsJson) {
    const items = []
    for (const [key, value] of Object.entries(objectsJson)) {
      if (key.startsWith('stars')) {
        // value is {constellation: [star, ...], ...}
        for (const [constellation, stars] of Object.entries(value)) {
          for (const star of stars) {
            const id = objectIdFromStar(star)
            if (id) items.push({ id, type: 'star', constellation, ...star })
          }
        }
      } else if (key === 'dso') {
        for (const [constellation, dsos] of Object.entries(value)) {
          for (const dso of dsos) {
            const id = objectIdFromDso(dso)
            if (id) items.push({ id, type: 'dso', constellation, ...dso })
          }
        }
      } else if (key === 'double_stars') {
        for (const [constellation, doubles] of Object.entries(value)) {
          if (!Array.isArray(doubles)) {
            console.error(`[parseObjects] double_stars["${constellation}"] is not an array:`, doubles)
            continue
          }
          for (const ds of doubles) {
            const id = ds.hip ? `double_HIP${ds.hip}` : (ds.hd ? `double_HD${ds.hd}` : null)
            if (id) items.push({ id, type: 'double_star', constellation, ...ds })
          }
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
    if (!username || !password) {
      errorMsg = 'Enter username and password'
      return
    }
    phase = 'loading'
    errorMsg = ''
    objectsProgress = 0
    imagesProgress = 0
    observationsDone = false

    try {
      // Step 1 — authenticate
      await login(username, password)

      // Step 2 — objects
      const objectsUrl = await getObjectsUrl()
      const objectsData = await fetchWithProgress(objectsUrl, p => { objectsProgress = p * 0.5 })

      const zip = await JSZip.loadAsync(objectsData, {
        onUpdate(metadata) {
          if (metadata.percent != null) objectsProgress = 0.5 + metadata.percent / 100 * 0.5
        }
      })

      const objectsFile = zip.file('objects.json')
      if (!objectsFile) throw new Error('objects.json not found in ZIP')
      const objectsJson = JSON.parse(await objectsFile.async('string'))

      const objectItems = parseObjects(objectsJson)
      await bulkPutObjects(objectItems)

      const metaKeys = extractMetaKeys(objectsJson)
      for (const [k, v] of Object.entries(metaKeys)) {
        await setMeta(k, v)
      }
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
      await bulkPutImages(imageItems)
      imagesProgress = 1

      // Step 4 — observations
      const observations = await getObservations()
      if (Array.isArray(observations) && observations.length > 0) {
        await bulkPutObservations(observations)
      }
      observationsDone = true

      phase = 'done'
      await push('/main')
    } catch (err) {
      console.error('[WelcomeScreen] handleLoad failed:', err)
      phase = 'error'
      errorMsg = err.message || String(err)
    }
  }
</script>

<div class="welcome-screen">
  <div class="welcome-card">
    <div class="app-title">Observarium</div>
    <div class="app-subtitle">Astronomy Field Notes</div>

    {#if phase === 'idle' || phase === 'error'}
      <p class="welcome-text">
        Welcome. Load your observation data to get started.
      </p>

      <div class="form">
        <label for="username-input">Username</label>
        <CustomInput id="username-input" bind:value={username} placeholder="username" />

        <label for="password-input">Password</label>
        <CustomInput id="password-input" bind:value={password} placeholder="password" mask={true} />

        {#if errorMsg}
          <div class="error-msg">{errorMsg}</div>
        {/if}

        <button class="load-btn" on:click={handleLoad}>Load Application Data</button>
      </div>
    {/if}

    {#if phase === 'loading' || phase === 'done'}
      <div class="phases">
        <div class="phase-row">
          <span class="phase-label">Objects</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {Math.round(objectsProgress * 100)}%"></div>
          </div>
          <span class="phase-pct">{Math.round(objectsProgress * 100)}%</span>
        </div>

        <div class="phase-row">
          <span class="phase-label">Images</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {Math.round(imagesProgress * 100)}%"></div>
          </div>
          <span class="phase-pct">{Math.round(imagesProgress * 100)}%</span>
        </div>

        <div class="phase-row">
          <span class="phase-label">Observations</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {observationsDone ? 100 : 0}%"></div>
          </div>
          <span class="phase-pct">{observationsDone ? '100' : '0'}%</span>
        </div>
      </div>

      {#if phase === 'loading'}
        <div class="loading-hint">Loading…</div>
      {:else}
        <div class="loading-hint">Complete — opening app…</div>
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
  margin-bottom: 1rem;
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
  width: 36px;
  text-align: right;
  font-size: 0.8rem;
  opacity: 0.6;
  font-variant-numeric: tabular-nums;
}

.loading-hint {
  margin-top: 1rem;
  font-size: 0.85rem;
  opacity: 0.55;
}
</style>
