<script>
  import { onMount, createEventDispatcher } from 'svelte'
  import { getCatalogueCounts } from '../lib/db.js'

  const dispatch = createEventDispatcher()
  const version = import.meta.env.VITE_APP_VERSION_DATE || '0.1.0'

  let counts = undefined  // undefined = loading, null = no data synced yet

  function close() { dispatch('close') }
  function handleKeydown(e) { if (e.key === 'Escape') close() }

  function fmt(n) {
    if (n == null) return '—'
    return n.toLocaleString()
  }

  $: val = (n) => counts === undefined ? '…' : fmt(counts?.[n])

  onMount(async () => {
    try {
      counts = await getCatalogueCounts()
    } catch (e) {
      console.error('[AboutPanel] getCatalogueCounts failed:', e)
      counts = null
    }
  })
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="backdrop" on:pointerdown|self={close} role="button" tabindex="-1" aria-label="Close About panel"></div>

<div class="panel" role="dialog" aria-modal="true" aria-label="About Observarium" on:pointerdown|stopPropagation>
  <div class="header">
    <div class="title-row">
      <svg class="app-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
        <circle cx="12" cy="12" r="9"/>
        <circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none"/>
        <line x1="12" y1="1" x2="12" y2="3.5"/>
        <line x1="12" y1="20.5" x2="12" y2="23"/>
        <line x1="1" y1="12" x2="3.5" y2="12"/>
        <line x1="20.5" y1="12" x2="23" y2="12"/>
      </svg>
      <span class="app-name">Observarium</span>
    </div>
    <button class="close-btn" on:click={close} aria-label="Close">✕</button>
  </div>

  <div class="body">
    <p class="tagline">A sky atlas for visual observers</p>
    <p class="version">Build {version}</p>

    <h3 class="section-head">Catalogue</h3>
    <dl class="counts">
      <dt>Stars</dt>             <dd>{val('stars')}</dd>
      <dt>Variable stars</dt>    <dd>{val('variableStars')}</dd>
      <dt>Double stars</dt>      <dd>{val('doubleStars')}</dd>
      <dt>Galaxies</dt>          <dd>{val('galaxies')}</dd>
      <dt>Open clusters</dt>     <dd>{val('openClusters')}</dd>
      <dt>Globular clusters</dt> <dd>{val('globularClusters')}</dd>
      <dt>Planetary nebulae</dt> <dd>{val('planetaryNebulae')}</dd>
      <dt>Other nebulae</dt>     <dd>{val('nebulae')}</dd>
      <dt>DSO images</dt>        <dd>{val('dsoImages')}</dd>
      <dt>Asteroids</dt>         <dd>{val('asteroids')}</dd>
    </dl>
  </div>
</div>

<style>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(0,0,0,0.55);
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
  box-shadow: 0 8px 40px rgba(0,0,0,0.6);
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 10px;
  border-bottom: 1px solid rgba(128,128,128,0.18);
  flex-shrink: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.app-icon {
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
.close-btn:hover { opacity: 0.9; }

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
  box-shadow: 0 8px 40px rgba(0,0,0,0.8);
}

:global([data-theme='nightly']) .header {
  border-bottom-color: rgba(180,0,0,0.25);
}

:global([data-theme='nightly']) .app-icon {
  color: #cc2200;
}
</style>
