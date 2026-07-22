<script>
  import { onMount, createEventDispatcher } from 'svelte'
  import { push } from 'svelte-spa-router'
  import LoginForm from './LoginForm.svelte'
  import OnScreenKeyboard from './OnScreenKeyboard.svelte'
  import { runSync, runUpdateSync, clearAllStarAndObjectData } from '../lib/datasync.js'
  import { getManifest } from '../lib/api.js'
  import { getTokenStatus } from '../lib/auth.js'
  import { getMeta } from '../lib/db.js'
  import { keyboardActive } from '../stores/keyboard.js'

  const dispatch = createEventDispatcher()

  // step machine: login | picker | updating | done | error
  let step = 'login'
  let errorMsg = ''
  let sessionExpired = false

  let availableSets = []
  let currentMag = null
  let syncDate = null

  let objectsProgress = 0
  let imagesProgress = 0
  let objectsSize = 0
  let imagesSize = 0
  let objectsUpToDate = false
  let imagesUpToDate = false
  let upToDate = false

  function formatSize(bytes) {
    if (bytes >= 1_000_000) return `${+(bytes / 1_000_000).toPrecision(2)} MB`
    if (bytes >= 1_000) return `${+(bytes / 1_000).toPrecision(2)} kB`
    return `${bytes} B`
  }

  function formatDate(isoStr) {
    if (!isoStr) return ''
    return new Date(isoStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  function close() {
    dispatch('close')
  }

  function handleKeydown(e) {
    if (e.key === 'Escape' && step !== 'updating') close()
    if (step === 'picker' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const idx = parseInt(e.key, 10) - 1
      if (!isNaN(idx) && idx >= 0 && idx < availableSets.length) {
        handleUpdate(availableSets[idx].mag)
      }
    }
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
      console.error('[DataSyncPanel] fetchManifest failed:', err)
      step = 'error'
      errorMsg = err.message || String(err)
    }
  }

  async function handleLoggedIn() {
    await fetchManifest()
  }

  async function handleUpdate(mag) {
    step = 'updating'
    errorMsg = ''
    sessionExpired = false
    objectsProgress = 0
    imagesProgress = 0
    objectsUpToDate = false
    imagesUpToDate = false
    upToDate = false

    const prevMag = localStorage.getItem('selectedMag')
    const prevMagNum = prevMag ? parseInt(prevMag, 10) : null
    const magChanged = prevMagNum !== null && prevMagNum !== mag

    if (magChanged) {
      await clearAllStarAndObjectData()
    }

    try {
      let result
      if (magChanged) {
        result = await runSync({
          mag,
          onObjectsProgress: (p) => {
            objectsProgress = p
          },
          onImagesProgress: (p) => {
            imagesProgress = p
          },
        })
        objectsUpToDate = false
        imagesUpToDate = false
        upToDate = false
      } else {
        result = await runUpdateSync({
          mag,
          onObjectsProgress: (p) => {
            objectsProgress = p
          },
          onImagesProgress: (p) => {
            imagesProgress = p
          },
        })
        objectsUpToDate = !!result.objectsUpToDate
        imagesUpToDate = !!result.imagesUpToDate
        upToDate = !!result.upToDate
      }
      objectsSize = result.objectsSize
      imagesSize = result.imagesSize
      localStorage.setItem('selectedMag', String(mag))
      step = 'done'
      dispatch('synced')
    } catch (err) {
      console.error('[DataSyncPanel] sync failed:', err)
      step = 'error'
      if (err.authExpired) {
        sessionStorage.removeItem('token')
        sessionExpired = true
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

  onMount(() => {
    const { valid, nearExpiry } = getTokenStatus()
    if (!valid || nearExpiry) {
      step = 'login'
    } else {
      fetchManifest()
    }
  })
</script>

<svelte:window on:keydown={handleKeydown} />

<div
  class="backdrop"
  on:pointerdown|self={() => {
    if (step !== 'updating') close()
  }}
  role="button"
  tabindex="-1"
  aria-label="Close"
></div>

<div class="panel" role="dialog" aria-modal="true" aria-label="Update Data" on:pointerdown|stopPropagation>
  <div class="header">
    <span class="title">Update Data</span>
    {#if step !== 'updating'}
      <button class="close-btn" on:click={close} aria-label="Close">✕</button>
    {/if}
  </div>

  <div class="body">
    {#if step === 'login'}
      <LoginForm submitLabel="Log In" on:loggedin={handleLoggedIn} />
    {/if}

    {#if step === 'picker'}
      <p class="picker-label">
        Select the option{#if currentMag != null && syncDate}
          (current data are up to magnitude {currentMag}, synchronized on {formatDate(syncDate)}){/if}:
      </p>
      <div class="picker">
        {#each availableSets as set, i (set.mag)}
          <button class="pick-row" on:click={() => handleUpdate(set.mag)}>
            <span class="pick-key">{i + 1}</span>
            <strong>Up to magnitude {set.mag}</strong><span class="pick-size"> ({formatSize(set.total_size)})</span>
          </button>
        {/each}
      </div>
    {/if}

    {#if step === 'updating' || step === 'done'}
      <div class="phases">
        <div class="phase-row">
          <span class="phase-label">Objects</span>
          {#if step === 'done' && objectsUpToDate}
            <span class="phase-up-to-date">Up to date</span>
          {:else}
            <div class="progress-track">
              <div class="progress-bar" style="width: {Math.round(objectsProgress * 100)}%"></div>
            </div>
            <span class="phase-pct"
              >{Math.round(objectsProgress * 100)}%{step === 'done' && objectsSize
                ? ` (${formatSize(objectsSize)})`
                : ''}</span
            >
          {/if}
        </div>

        <div class="phase-row">
          <span class="phase-label">Images</span>
          {#if step === 'done' && imagesUpToDate}
            <span class="phase-up-to-date">Up to date</span>
          {:else}
            <div class="progress-track">
              <div class="progress-bar" style="width: {Math.round(imagesProgress * 100)}%"></div>
            </div>
            <span class="phase-pct"
              >{Math.round(imagesProgress * 100)}%{step === 'done' && imagesSize
                ? ` (${formatSize(imagesSize)})`
                : ''}</span
            >
          {/if}
        </div>

        <div class="phase-row">
          <span class="phase-label">User data</span>
          <span class="phase-up-to-date">Up to date</span>
        </div>
      </div>

      {#if step === 'updating'}
        <p class="status-msg">Updating…</p>
      {:else}
        <p class="status-msg success">{upToDate ? 'Everything is up to date.' : 'Data updated successfully.'}</p>
      {/if}
    {/if}

    {#if step === 'error'}
      <p class="error-msg">{errorMsg}</p>
      <div class="actions">
        {#if sessionExpired}
          <button
            class="action-btn primary"
            on:click={() => {
              close()
              push('/')
            }}>Log in</button
          >
        {:else}
          <button class="action-btn primary" on:click={handleRetry}>Retry</button>
          <button class="action-btn" on:click={close}>Close</button>
        {/if}
      </div>
    {/if}
  </div>
</div>

{#if $keyboardActive}
  <div class="kb-dock" on:pointerdown|stopPropagation>
    <OnScreenKeyboard />
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 50;
    background: rgba(0, 0, 0, 0.55);
  }

  .kb-dock {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 52;
    padding: 0.5rem;
    box-sizing: border-box;
    background: var(--surface-bg);
  }

  .panel {
    position: fixed;
    z-index: 51;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(420px, calc(100vw - 32px));
    background: var(--surface-bg);
    color: var(--surface-fg);
    border-radius: 14px;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6);
    display: flex;
    flex-direction: column;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 16px 12px;
    border-bottom: 1px solid rgba(128, 128, 128, 0.18);
    flex-shrink: 0;
  }

  .title {
    font-size: 1rem;
    font-weight: 600;
  }

  .close-btn {
    background: none;
    border: none;
    color: inherit;
    opacity: 0.5;
    font-size: 1rem;
    cursor: pointer;
    padding: 4px 6px;
    border-radius: 6px;
    line-height: 1;
    transition: opacity 120ms;
  }
  .close-btn:hover {
    opacity: 0.9;
  }

  .body {
    padding: 16px 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .picker {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .picker-label {
    margin: 0;
    font-size: 0.85rem;
    opacity: 0.7;
    line-height: 1.4;
  }

  .pick-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0.75rem;
    border-radius: 6px;
    border: 1px solid rgba(127, 127, 127, 0.2);
    background: none;
    color: inherit;
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

  .pick-size {
    font-size: 0.8rem;
    opacity: 0.6;
    font-variant-numeric: tabular-nums;
  }

  .pick-key {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.3em;
    height: 1.3em;
    font-size: 0.75rem;
    border: 1px solid rgba(127, 127, 127, 0.35);
    border-radius: 3px;
    opacity: 0.65;
    margin-right: 0.5rem;
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }

  .phases {
    display: flex;
    flex-direction: column;
    gap: 10px;
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

  .phase-up-to-date {
    margin-left: auto;
    font-size: 0.85rem;
    color: var(--fg);
    opacity: 0.85;
  }

  .status-msg {
    margin: 0;
    font-size: 0.85rem;
    opacity: 0.65;
  }

  .status-msg.success {
    opacity: 0.85;
  }

  .error-msg {
    margin: 0;
    font-size: 0.85rem;
    color: var(--accent);
    word-break: break-word;
  }

  .actions {
    display: flex;
    gap: 8px;
  }

  .action-btn {
    padding: 0.55rem 1rem;
    font-size: 0.9rem;
    cursor: pointer;
    border-radius: 6px;
    border: 1px solid rgba(127, 127, 127, 0.25);
    background: none;
    color: inherit;
    transition: opacity 120ms;
  }
  .action-btn:hover {
    opacity: 0.8;
  }
  .action-btn:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .action-btn.primary {
    border-color: rgba(127, 127, 127, 0.45);
    font-weight: 600;
  }

  :global([data-theme='nightly']) .panel {
    background: #110000;
    color: #ff8080;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.8);
  }

  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(180, 0, 0, 0.25);
  }
</style>
