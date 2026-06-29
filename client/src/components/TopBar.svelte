<script>
  import { createEventDispatcher, onMount, onDestroy } from 'svelte'
  import { selectedObject } from '../stores/selectedObject.js'
  import { searchViewActive } from '../stores/ui.js'
  import ObservationObjectSymbol from './ObservationObjectSymbol.svelte'
  import HamburgerIcon from '../icons/HamburgerIcon.svelte'
  import SearchIcon from '../icons/SearchIcon.svelte'

  export let time = new Date()
  export let menuOpen = false
  export let finderMode = false

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

  function dsLetterCount(pairs) {
    if (!Array.isArray(pairs)) return 0
    const letters = new Set()
    for (const p of pairs)
      for (const c of String(p.comp || ''))
        if (c >= 'A' && c <= 'Z') letters.add(c)
    return letters.size
  }

  function objectSymbolKind(obj) {
    if (!obj) return 'generic'
    if (obj.type === 'double_star') return dsLetterCount(obj.pairs) > 2 ? 'double_star_multi' : 'double_star'
    if (obj.type === 'star') {
      if (obj.dbl === 'm') return 'double_star_multi'
      if (obj.dbl) return 'double_star'
      return 'star'
    }
    if (obj.type === 'solar_system_body') return String(obj.name || '').toLowerCase() || 'generic'

    const type = String(obj.dsoType || '').toLowerCase()
    if (type === 'open cluster') return 'open_cluster'
    if (type === 'globular cluster') return 'globular_cluster'
    if (type === 'planetary nebula') return 'planetary_nebula'
    if (type === 'spiral galaxy' || type === 'elliptical galaxy' || type === 'galaxy') return 'galaxy'
    if (type === 'dark nebula') return 'dark_nebula'
    if (type === 'galaxy cluster' || type === 'cluster of galaxies') return 'galaxy_cluster'
    if (type === 'quasar' || type === 'qso' || type === 'bl lac') return 'quasar'
    if (type.includes('nebula')) return 'nebula'
    return 'generic'
  }

  function battFillW(level) {
    return Math.max(0, Math.round((13 * level) / 100))
  }

  function greekFromBayer(bayer) {
    const raw = String(bayer || '').trim()
    if (!raw) return null
    const first = raw.split(/\s+/)[0] || ''
    const cleaned = first
      .toLowerCase()
      .replace(/[0-9]+$/g, '')
      .replace(/[._-]+$/g, '')
    const greekChars = 'αβγδεζηθικλμνξοπρστυφχψω'
    if (cleaned && greekChars.includes(cleaned[0])) return cleaned[0]
    const key = cleaned.length >= 3 ? cleaned.slice(0, 3) : cleaned
    const map = {
      alf: 'α',
      alp: 'α',
      bet: 'β',
      gam: 'γ',
      del: 'δ',
      eps: 'ε',
      zet: 'ζ',
      eta: 'η',
      the: 'θ',
      iot: 'ι',
      kap: 'κ',
      lam: 'λ',
      mu: 'μ',
      nu: 'ν',
      xi: 'ξ',
      omi: 'ο',
      pi: 'π',
      rho: 'ρ',
      sig: 'σ',
      tau: 'τ',
      ups: 'υ',
      phi: 'φ',
      chi: 'χ',
      psi: 'ψ',
      ome: 'ω',
    }
    return map[key] || null
  }

  function preferredStarLabel(obj) {
    const rawName = String(obj?.name || '').trim()
    if (rawName) return rawName
    const rawBay = String(obj?.bay || '').trim()
    const greek = greekFromBayer(obj?.bay)
    if (greek && obj?.constellation) return `${greek} ${obj.constellation}`
    if (rawBay && obj?.constellation) return `${rawBay} ${obj.constellation}`
    if (obj?.hip != null) return `HIP ${obj.hip}`
    if (obj?.hd != null) return `HD ${obj.hd}`
    if (obj?.sao != null) return `SAO ${obj.sao}`
    if (obj?.flam != null && obj?.constellation) return `${obj.flam} ${obj.constellation}`
    return String(obj?.id || 'Star')
  }

  function primaryCatalogueLabel(obj) {
    if (!obj) return ''
    if (obj.type === 'star') return preferredStarLabel(obj)
    if (obj.m != null) return `M ${obj.m}`
    if (obj.ngc != null) return `NGC ${obj.ngc}`
    if (obj.ic != null) return `IC ${obj.ic}`
    if (obj.caldwell != null) return `C ${obj.caldwell}`
    if (obj.hip != null) return `HIP ${obj.hip}`
    if (obj.hd != null) return `HD ${obj.hd}`
    if (obj.sao != null) return `SAO ${obj.sao}`
    if (obj.bay && obj.constellation) return `${obj.bay} ${obj.constellation}`
    if (obj.flam && obj.constellation) return `${obj.flam} ${obj.constellation}`
    const id = String(obj.id || '')
    if (id.startsWith('dso_M')) return `M ${Number(id.slice(5))}`
    if (id.startsWith('dso_NGC')) return `NGC ${Number(id.slice(7))}`
    if (id.startsWith('dso_IC')) return `IC ${Number(id.slice(6))}`
    if (id.startsWith('dso_C')) return `C ${Number(id.slice(5))}`
    if (id.startsWith('solar_')) {
      const name = id.slice(6).replace(/_/g, ' ').trim()
      return name ? name[0].toUpperCase() + name.slice(1) : 'Solar object'
    }
    if (obj.name) return obj.name
    return id.replace(/^star_([A-Za-z]+)(\d+)$/, '$1 $2')
  }

  function objLabel(obj) {
    if (!obj) return ''
    if (obj.type === 'star') return preferredStarLabel(obj)
    const catalogue = primaryCatalogueLabel(obj)
    const rawName = String(obj.name || '').trim()
    if (!rawName) return catalogue
    if (rawName.toLowerCase() === String(catalogue).toLowerCase()) return catalogue
    return `${catalogue} (${rawName})`
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
        <HamburgerIcon />
      </button>
      <button class="search-btn" on:click={() => dispatch('searchtoggle')} aria-label="Search">
        <SearchIcon />
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

  {#if $selectedObject && !menuOpen && !$searchViewActive && !finderMode}
    <div
      class="row2"
      role="button"
      tabindex="0"
      on:click={() => dispatch('objectdetails')}
      on:keydown={(e) => e.key === 'Enter' && dispatch('objectdetails')}
    >
      <span class="obj-icon"><ObservationObjectSymbol kind={objectSymbolKind($selectedObject)} /></span>
      <span class="obj-name">{objLabel($selectedObject)}</span>
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
</style>
