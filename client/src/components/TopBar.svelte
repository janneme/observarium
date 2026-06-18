<script>
  import { createEventDispatcher, onMount, onDestroy } from 'svelte'
  import { selectedObject } from '../stores/selectedObject.js'
  import { searchViewActive } from '../stores/ui.js'

  export let time = new Date()
  export let menuOpen = false

  const dispatch = createEventDispatcher()

  let battery = null
  let batteryLevel = null

  function formatDate(d) {
    const mon = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()]
    return `${d.getDate()} ${mon}`
  }

  function formatTime(d) {
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }

  function onBatteryUpdate() {
    batteryLevel = Math.round(battery.level * 100)
  }

  onMount(async () => {
    try {
      battery = await navigator.getBattery()
      onBatteryUpdate()
      battery.addEventListener('levelchange', onBatteryUpdate)
      battery.addEventListener('chargingchange', onBatteryUpdate)
    } catch {
      // getBattery() not supported
    }
  })

  onDestroy(() => {
    if (battery) {
      battery.removeEventListener('levelchange', onBatteryUpdate)
      battery.removeEventListener('chargingchange', onBatteryUpdate)
    }
  })

  function objIcon(obj) {
    if (!obj) return ''
    if (obj.type === 'double_star') return '⊛'
    if (obj.type === 'star') return '★'
    const dt = obj.dsoType || ''
    if (dt === 'Gx' || dt.includes('galaxy')) return '⊛'
    if (dt === 'OC') return '⊕'
    if (dt === 'GC') return '⊗'
    if (dt === 'Nb' || dt.includes('nebula')) return '◎'
    return '◉'
  }

  function battFillW(level) {
    return Math.max(0, Math.round((13 * level) / 100))
  }
</script>

<div class="top-bar" on:pointerdown|stopPropagation>
  <div class="row1">
    <button class="datetime-btn" on:click={() => dispatch('timepick')}>
      <span class="dt-date">{formatDate(time)}</span>
      <span class="dt-sep"> </span>
      <span class="dt-time">{formatTime(time)}</span>
    </button>

    <div class="center-group">
      <button class="menu-btn" on:click={() => dispatch('menutoggle')} aria-label="Menu">
        <svg width="22" height="16" viewBox="0 0 22 16" fill="none">
          <line x1="1" y1="2" x2="21" y2="2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          <line x1="1" y1="8" x2="21" y2="8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          <line x1="1" y1="14" x2="21" y2="14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
        </svg>
      </button>
      <button class="search-btn" on:click={() => dispatch('searchtoggle')} aria-label="Search">
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
        >
          <circle cx="10.5" cy="10.5" r="6.5" />
          <line x1="15.5" y1="15.5" x2="21" y2="21" />
        </svg>
      </button>
    </div>

    <div class="battery-area">
      {#if batteryLevel !== null}
        <svg class="batt-icon" width="18" height="10" viewBox="0 0 18 10">
          <rect x="0.5" y="0.5" width="14" height="9" rx="2" stroke="currentColor" stroke-width="1" fill="none" />
          <rect x="14.5" y="2.5" width="2.5" height="5" rx="1" fill="currentColor" />
          <rect x="1.5" y="1.5" width={battFillW(batteryLevel)} height="7" rx="1" fill="currentColor" />
        </svg>
        <span class="batt-pct">{batteryLevel}%</span>
      {:else}
        <span class="batt-unknown">—</span>
      {/if}
    </div>
  </div>

  {#if $selectedObject && !menuOpen && !$searchViewActive}
    <div
      class="row2"
      role="button"
      tabindex="0"
      on:click={() => selectedObject.set(null)}
      on:keydown={(e) => e.key === 'Enter' && selectedObject.set(null)}
    >
      <span class="obj-icon">{objIcon($selectedObject)}</span>
      <span class="obj-name">{$selectedObject.name || $selectedObject.id}</span>
      {#if $selectedObject.constellation}
        <span class="obj-const">{$selectedObject.constellation}</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .top-bar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 10;
    background: var(--surface-bg);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    color: var(--surface-fg);
  }

  .row1 {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    height: 2.75rem;
    padding: 0 0.6rem;
  }

  .datetime-btn {
    background: none;
    border: none;
    color: inherit;
    padding: 0;
    display: flex;
    align-items: baseline;
    gap: 0;
    font-size: 0.82rem;
    cursor: pointer;
    text-align: left;
  }

  .dt-date {
    opacity: 0.6;
  }
  .dt-sep {
    width: 0.4em;
  }
  .dt-time {
    font-variant-numeric: tabular-nums;
  }

  .center-group {
    display: flex;
    align-items: center;
  }

  .menu-btn {
    background: none;
    border: none;
    color: inherit;
    padding: 0.4rem 0.6rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .search-btn {
    background: none;
    border: none;
    color: inherit;
    padding: 0.4rem 0.5rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0.75;
  }

  .search-btn:hover {
    opacity: 1;
  }

  .battery-area {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.3rem;
    font-size: 0.78rem;
    opacity: 0.7;
  }

  .batt-icon {
    flex-shrink: 0;
  }
  .batt-pct {
    font-variant-numeric: tabular-nums;
  }
  .batt-unknown {
    opacity: 0.4;
  }

  .row2 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    height: 2rem;
    padding: 0 0.75rem;
    border-top: 1px solid rgba(127, 127, 127, 0.12);
    font-size: 0.82rem;
    cursor: pointer;
  }

  .row2:hover {
    background: rgba(127, 127, 127, 0.06);
  }

  .obj-icon {
    font-size: 0.85rem;
    opacity: 0.75;
    flex-shrink: 0;
  }
  .obj-name {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .obj-const {
    opacity: 0.45;
    font-size: 0.75rem;
    flex-shrink: 0;
  }
</style>
