<script>
  import { onMount } from 'svelte'
  import { push } from 'svelte-spa-router'
  import LoginForm from '../components/LoginForm.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import { runSync, clearAllStarAndObjectData } from '../lib/datasync.js'
  import { getManifest } from '../lib/api.js'
  import { getTokenStatus } from '../lib/auth.js'
  import { getMeta } from '../lib/db.js'
  import { keyboardActive } from '../stores/keyboard.js'

  const appVersion = import.meta.env.VITE_APP_VERSION_DATE || 'dev'

  // step machine: login | picker | downloading | done | error
  let step = 'login'
  let errorMsg = ''

  let availableSets = []
  let currentMag = null
  let syncDate = null

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

  function formatDate(isoStr) {
    if (!isoStr) return ''
    return new Date(isoStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  async function fetchManifest() {
    try {
      const [manifest, storedSyncDate] = await Promise.all([getManifest(), getMeta('syncDate')])
      availableSets = manifest.sets || []
      const savedMag = localStorage.getItem('selectedMag')
      currentMag = savedMag ? parseInt(savedMag, 10) : null
      syncDate = storedSyncDate ?? null
      step = 'picker'
    } catch (err) {
      console.error('[WelcomeScreen] fetchManifest failed:', err)
      step = 'error'
      errorMsg = err.message || String(err)
    }
  }

  async function handleLoggedIn() {
    await fetchManifest()
  }

  async function handleDownload(mag) {
    step = 'downloading'
    errorMsg = ''
    objectsProgress = 0
    imagesProgress = 0
    observationsDone = false

    const prevMag = localStorage.getItem('selectedMag')
    const prevMagNum = prevMag ? parseInt(prevMag, 10) : null
    if (prevMagNum !== null && prevMagNum !== mag) {
      await clearAllStarAndObjectData()
    }

    try {
      const result = await runSync({
        mag,
        onObjectsProgress: (p) => {
          objectsProgress = p
        },
        onImagesProgress: (p) => {
          imagesProgress = p
        },
        onObservationsDone: () => {
          observationsDone = true
        },
      })
      objectsSize = result.objectsSize
      imagesSize = result.imagesSize
      observationsSize = result.observationsSize
      localStorage.setItem('selectedMag', String(mag))
      step = 'done'
    } catch (err) {
      console.error('[WelcomeScreen] runSync failed:', err)
      step = 'error'
      if (err.authExpired) {
        sessionStorage.removeItem('token')
        errorMsg = 'Session expired. Please log in again.'
      } else {
        errorMsg = err.message || String(err)
      }
    }
  }

  function handleRetry() {
    const { valid, nearExpiry } = getTokenStatus()
    if (!valid || nearExpiry) {
      step = 'login'
    } else {
      fetchManifest()
    }
  }

  async function handleContinue() {
    await push('/main')
  }

  onMount(() => {
    const { valid, nearExpiry } = getTokenStatus()
    if (!valid || nearExpiry) {
      step = 'login'
    } else {
      fetchManifest()
    }
  })
</script>

<div class="welcome-screen">
  <div class="welcome-card">
    <div class="app-title">Observarium</div>
    <div class="app-subtitle">Astronomy Field Notes</div>
    <div class="app-version">v{appVersion}</div>

    <p class="app-description">
      Mobile astronomy companion — identify sky objects, find them through the finder scope, track observations, and
      test your knowledge with quizzes.
    </p>

    {#if step === 'login'}
      <p class="welcome-text">Welcome. Please log in to continue.</p>
      <div class="form">
        <LoginForm submitLabel="Log In" on:loggedin={handleLoggedIn} />
      </div>
    {/if}

    {#if step === 'picker'}
      <p class="welcome-text">
        Select the option{#if currentMag != null && syncDate}
          (current data are up to magnitude {currentMag}, synchronized on {formatDate(syncDate)}){/if}:
      </p>
      <div class="picker">
        {#each availableSets as set (set.mag)}
          <button class="pick-row" on:click={() => handleDownload(set.mag)}>
            <span class="pick-mag">Magnitude ≤ {set.mag}</span>
            <span class="pick-size">{formatSize(set.total_size)}</span>
          </button>
        {/each}
      </div>
    {/if}

    {#if step === 'downloading' || step === 'done'}
      <div class="phases">
        <div class="phase-row">
          <span class="phase-label">Objects</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {Math.round(objectsProgress * 100)}%"></div>
          </div>
          <span class="phase-pct"
            >{Math.round(objectsProgress * 100)}%{step === 'done' && objectsSize
              ? ` (${formatSize(objectsSize)})`
              : ''}</span
          >
        </div>

        <div class="phase-row">
          <span class="phase-label">Images</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {Math.round(imagesProgress * 100)}%"></div>
          </div>
          <span class="phase-pct"
            >{Math.round(imagesProgress * 100)}%{step === 'done' && imagesSize
              ? ` (${formatSize(imagesSize)})`
              : ''}</span
          >
        </div>

        <div class="phase-row">
          <span class="phase-label">Observations</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {observationsDone ? 100 : 0}%"></div>
          </div>
          <span class="phase-pct"
            >{observationsDone ? '100' : '0'}%{step === 'done' && observationsSize
              ? ` (${formatSize(observationsSize)})`
              : ''}</span
          >
        </div>
      </div>

      {#if step === 'downloading'}
        <div class="loading-hint">Loading…</div>
      {:else}
        <button class="load-btn" on:click={handleContinue}>Continue</button>
      {/if}
    {/if}

    {#if step === 'error'}
      <div class="error-msg">{errorMsg}</div>
      <button class="load-btn" on:click={handleRetry}>Retry</button>
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

  .picker {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .pick-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0.75rem;
    border-radius: 6px;
    border: 1px solid rgba(127, 127, 127, 0.2);
    background: none;
    color: var(--fg);
    cursor: pointer;
    font-size: 0.9rem;
    transition:
      border-color 120ms,
      background 120ms;
    text-align: left;
  }

  .pick-row:hover {
    border-color: rgba(127, 127, 127, 0.55);
    background: rgba(127, 127, 127, 0.06);
  }

  .pick-mag {
    font-weight: 500;
  }

  .pick-size {
    font-size: 0.8rem;
    opacity: 0.6;
    font-variant-numeric: tabular-nums;
  }

  .error-msg {
    font-size: 0.85rem;
    color: var(--accent);
    padding: 0.25rem 0;
    margin-bottom: 0.5rem;
  }

  .load-btn {
    margin-top: 0.75rem;
    padding: 0.65rem 1rem;
    font-size: 1rem;
    cursor: pointer;
    border-radius: 6px;
    border: 1px solid rgba(127, 127, 127, 0.25);
    background: none;
    color: var(--fg);
    transition: opacity 120ms ease;
    width: 100%;
  }

  .load-btn:hover {
    opacity: 0.8;
  }

  .load-btn:disabled {
    opacity: 0.35;
    cursor: default;
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
    background: rgba(127, 127, 127, 0.15);
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
