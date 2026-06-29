<script>
  import { push } from 'svelte-spa-router'
  import LoginForm from '../components/LoginForm.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import { runSync } from '../lib/datasync.js'
  import { keyboardActive } from '../stores/keyboard.js'

  const appVersion = import.meta.env.VITE_APP_VERSION_DATE || 'dev'

  let hasToken = !!sessionStorage.getItem('token')

  let phase = 'idle' // idle | loading | done | error
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

  async function runDataSync() {
    phase = 'loading'
    errorMsg = ''
    objectsProgress = 0
    imagesProgress = 0
    observationsDone = false

    try {
      const result = await runSync({
        onObjectsProgress: (p) => { objectsProgress = p },
        onImagesProgress: (p) => { imagesProgress = p },
        onObservationsDone: () => { observationsDone = true },
      })
      objectsSize = result.objectsSize
      imagesSize = result.imagesSize
      observationsSize = result.observationsSize
      phase = 'done'
    } catch (err) {
      console.error('[WelcomeScreen] runDataSync failed:', err)
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
      Mobile astronomy companion — identify sky objects, find them through the finder scope, track observations, and
      test your knowledge with quizzes.
    </p>

    {#if phase === 'idle' || phase === 'error'}
      <p class="welcome-text">Welcome. Load your observation data to get started.</p>

      {#if !hasToken}
        <div class="form">
          {#if errorMsg}
            <div class="error-msg">{errorMsg}</div>
          {/if}
          <LoginForm submitLabel="Load Application Data" on:loggedin={runDataSync} />
        </div>
      {:else}
        {#if errorMsg}
          <div class="error-msg">{errorMsg}</div>
        {/if}
        <button class="load-btn" on:click={runDataSync}>Load Application Data</button>
      {/if}
    {/if}

    {#if phase === 'loading' || phase === 'done'}
      <div class="phases">
        <div class="phase-row">
          <span class="phase-label">Objects</span>
          <div class="progress-track">
            <div class="progress-bar" style="width: {Math.round(objectsProgress * 100)}%"></div>
          </div>
          <span class="phase-pct"
            >{Math.round(objectsProgress * 100)}%{phase === 'done' && objectsSize
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
            >{Math.round(imagesProgress * 100)}%{phase === 'done' && imagesSize
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
            >{observationsDone ? '100' : '0'}%{phase === 'done' && observationsSize
              ? ` (${formatSize(observationsSize)})`
              : ''}</span
          >
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
    border: 1px solid rgba(127, 127, 127, 0.25);
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
