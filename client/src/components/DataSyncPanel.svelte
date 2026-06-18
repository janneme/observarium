<script>
  import { onMount, createEventDispatcher } from 'svelte'
  import { push } from 'svelte-spa-router'
  import { runSync } from '../lib/datasync.js'

  const dispatch = createEventDispatcher()

  let phase = 'loading' // loading | done | error
  let errorMsg = ''
  let sessionExpired = false

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

  function close() {
    dispatch('close')
  }

  function handleKeydown(e) {
    if (e.key === 'Escape' && phase !== 'loading') close()
  }

  async function startSync() {
    phase = 'loading'
    errorMsg = ''
    sessionExpired = false
    objectsProgress = 0
    imagesProgress = 0
    observationsDone = false

    try {
      const result = await runSync({
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
      phase = 'done'
    } catch (err) {
      console.error('[DataSyncPanel] sync failed:', err)
      phase = 'error'
      if (err.message && err.message.includes('401')) {
        sessionStorage.removeItem('token')
        sessionExpired = true
        errorMsg = 'Session expired. Please log in again.'
      } else {
        errorMsg = err.message || String(err)
      }
    }
  }

  onMount(startSync)
</script>

<svelte:window on:keydown={handleKeydown} />

<div
  class="backdrop"
  on:pointerdown|self={() => {
    if (phase !== 'loading') close()
  }}
  role="button"
  tabindex="-1"
  aria-label="Close"
></div>

<div class="panel" role="dialog" aria-modal="true" aria-label="Update Data" on:pointerdown|stopPropagation>
  <div class="header">
    <span class="title">Update Data</span>
    {#if phase !== 'loading'}
      <button class="close-btn" on:click={close} aria-label="Close">✕</button>
    {/if}
  </div>

  <div class="body">
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
      <p class="status-msg">Updating…</p>
    {:else if phase === 'done'}
      <p class="status-msg success">Data updated successfully.</p>
    {:else if phase === 'error'}
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
          <button class="action-btn primary" on:click={startSync}>Retry</button>
          <button class="action-btn" on:click={close}>Close</button>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 50;
    background: rgba(0, 0, 0, 0.55);
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
