<script>
  import { onMount, createEventDispatcher } from 'svelte'
  import { getAboutStats } from '../lib/db.js'
  import AppIcon from '../icons/AppIcon.svelte'

  const dispatch = createEventDispatcher()
  const version = import.meta.env.VITE_APP_VERSION_DATE || '0.1.0'

  let stats = undefined

  function close() {
    dispatch('close')
  }
  function handleKeydown(e) {
    if (e.key === 'Escape') close()
  }

  function fmt(n) {
    if (n == null) return '—'
    return n.toLocaleString()
  }

  function fmtBytes(bytes) {
    if (bytes == null) return '—'
    if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(2)} GB`
    if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(2)} MB`
    if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} kB`
    return `${bytes} B`
  }

  $: val = (n) => (stats === undefined ? '…' : fmt(stats?.[n]))
  $: valBytes = (n) => (stats === undefined ? '…' : fmtBytes(stats?.[n]))

  onMount(async () => {
    try {
      stats = await getAboutStats()
    } catch (e) {
      console.error('[AboutPanel] getAboutStats failed:', e)
      stats = null
    }
  })
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="backdrop" on:pointerdown|self={close} role="button" tabindex="-1" aria-label="Close About panel"></div>

<div class="panel" role="dialog" aria-modal="true" aria-label="About Observarium" on:pointerdown|stopPropagation>
  <div class="header">
    <div class="title-row">
      <AppIcon size="28" class="app-icon" />
      <span class="app-name">Observarium</span>
    </div>
    <button class="close-btn" on:click={close} aria-label="Close">✕</button>
  </div>

  <div class="body">
    <p class="tagline">A sky atlas for visual observers</p>
    <p class="version">Build {version}</p>

    <h3 class="section-head">Data size</h3>
    <dl class="counts">
      <dt>Object data</dt>
      <dd>{valBytes('objectDataBytes')}</dd>
      <dt>Images</dt>
      <dd>{valBytes('imagesBytes')}</dd>
      <dt>User data</dt>
      <dd>{valBytes('userDataBytes')}</dd>
      <dt>Total local (estimated)</dt>
      <dd>{valBytes('totalEstimatedBytes')}</dd>
    </dl>

    <h3 class="section-head">Objects</h3>
    <dl class="counts">
      <dt>Stars</dt>
      <dd>{val('starsCount')}</dd>
      <dt>Deep sky objects</dt>
      <dd>{val('dsoCount')}</dd>
      <dt>Defined finding paths</dt>
      <dd>{val('findingPathsCount')}</dd>
    </dl>

    <h3 class="section-head">Observations</h3>
    <dl class="counts">
      <dt>Observations</dt>
      <dd>{val('observationsCount')}</dd>
      <dt>Observed objects</dt>
      <dd>{val('observedObjectsCount')}</dd>
      <dt>Unique observed objects</dt>
      <dd>{val('uniqueObservedObjectsCount')}</dd>
    </dl>
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
    max-height: calc(100vh - 64px);
    overflow-y: auto;
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
    padding: 16px 16px 10px;
    border-bottom: 1px solid rgba(128, 128, 128, 0.18);
    flex-shrink: 0;
  }

  .title-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  :global(.app-icon) {
    width: 28px;
    height: 28px;
    color: var(--accent);
    flex-shrink: 0;
  }

  .app-name {
    font-size: 1.15rem;
    font-weight: 600;
    letter-spacing: 0.01em;
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
    padding: 14px 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .tagline {
    margin: 0;
    font-size: 0.88rem;
    opacity: 0.7;
  }

  .version {
    margin: 0 0 4px;
    font-size: 0.75rem;
    opacity: 0.4;
    font-variant-numeric: tabular-nums;
  }

  .section-head {
    margin: 10px 0 6px;
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    opacity: 0.5;
  }

  .counts {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 5px 16px;
    margin: 0;
  }

  .counts dt {
    font-size: 0.82rem;
    opacity: 0.7;
  }

  .counts dd {
    margin: 0;
    font-size: 0.82rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  :global([data-theme='nightly']) .panel {
    background: #110000;
    color: #ff8080;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.8);
  }

  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(180, 0, 0, 0.25);
  }

  :global([data-theme='nightly'] .app-icon) {
    color: #cc2200;
  }
</style>
