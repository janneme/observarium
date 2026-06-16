<script>
  import { createEventDispatcher } from 'svelte'

  const dispatch = createEventDispatcher()
  const version = import.meta.env.VITE_APP_VERSION_DATE || '0.1.0'

  function close() { dispatch('close') }
  function handleKeydown(e) { if (e.key === 'Escape') close() }
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

    <h3 class="section-head">Data sources</h3>
    <ul class="credits">
      <li>
        <span class="src-name">Stars</span>
        AT-HYG v3.3 (Tycho-2 + Hipparcos + Yale GC) &amp; Gaia DR3 supplement
        <span class="licence">astronexus · CC-BY-SA 4.0</span>
      </li>
      <li>
        <span class="src-name">Deep sky objects</span>
        OpenNGC
        <span class="licence">Mattia Verga · CC-BY-SA 4.0</span>
      </li>
      <li>
        <span class="src-name">Constellation lines &amp; boundaries</span>
        Stellarium modern sky culture
        <span class="licence">Stellarium contributors · GPL v2</span>
      </li>
      <li>
        <span class="src-name">Double stars</span>
        Washington Double Star Catalog (WDS) via VizieR
        <span class="licence">US Naval Observatory · public domain</span>
      </li>
      <li>
        <span class="src-name">Moon features</span>
        USGS / IAU Gazetteer of Planetary Nomenclature
        <span class="licence">public domain</span>
      </li>
    </ul>
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

.credits {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.credits li {
  font-size: 0.82rem;
  line-height: 1.45;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.src-name {
  font-weight: 600;
  font-size: 0.8rem;
}

.licence {
  font-size: 0.72rem;
  opacity: 0.45;
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
