<script>
  import { createEventDispatcher, onMount, onDestroy } from 'svelte'
  import { selectedObject } from '../stores/selectedObject.js'
  import { searchViewActive, finderViewActive } from '../stores/ui.js'
  import { theme, toggleTheme } from '../stores/theme.js'
  import ObservationObjectSymbol from './ObservationObjectSymbol.svelte'
  import HamburgerIcon from '../icons/HamburgerIcon.svelte'
  import SearchIcon from '../icons/SearchIcon.svelte'
  import FinderViewIcon from '../icons/FinderViewIcon.svelte'
  import NightModeIcon from '../icons/NightModeIcon.svelte'
  import { getDoubleStarNear } from '../lib/db.js'

  export let time = new Date()
  export let menuOpen = false
  export let finderMode = false
  export let fov = null
  export let magMin = null
  export let magMax = null

  let linkedDs = null

  $: {
    const obj = $selectedObject
    if (obj?.type === 'star' && obj?.dbl && !Array.isArray(obj.dbl)) {
      linkedDs = null
      getDoubleStarNear(obj.pos[0], obj.pos[1]).then((ds) => {
        if ($selectedObject?.id === obj.id) linkedDs = ds
      })
    } else {
      linkedDs = null
    }
  }

  const dispatch = createEventDispatcher()

  let battery = null
  let batteryLevel = null
  let isFullscreen = false
  let fullscreenSupported = false

  function onFullscreenChange() {
    isFullscreen = !!(document.fullscreenElement || document.webkitFullscreenElement)
  }

  function enterFullscreen() {
    const el = document.documentElement
    const fn = el.requestFullscreen ?? el.webkitRequestFullscreen
    fn?.call(el).catch(() => {})
  }

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
    fullscreenSupported = !!(document.fullscreenEnabled || document.webkitFullscreenEnabled)
    document.addEventListener('fullscreenchange', onFullscreenChange)
    document.addEventListener('webkitfullscreenchange', onFullscreenChange)
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
    document.removeEventListener('fullscreenchange', onFullscreenChange)
    document.removeEventListener('webkitfullscreenchange', onFullscreenChange)
    if (battery) {
      battery.removeEventListener('levelchange', onBatteryUpdate)
      battery.removeEventListener('chargingchange', onBatteryUpdate)
    }
  })

  function dsLetterCount(pairs) {
    if (!Array.isArray(pairs)) return 0
    const letters = new Set()
    for (const p of pairs) for (const c of String(p.comp || '')) if (c >= 'A' && c <= 'Z') letters.add(c)
    return letters.size
  }

  function objectSymbolKind(obj) {
    if (!obj) return 'generic'
    if (obj.type === 'double_star') return dsLetterCount(obj.pairs) > 2 ? 'double_star_multi' : 'double_star'
    if (obj.type === 'star') {
      if (obj.dbl === 'm') return 'double_star_multi'
      if (obj.dbl) return 'double_star'
      if (Array.isArray(obj.mag) && obj.mag[1] - obj.mag[0] >= 1) return 'variable_star'
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

  $: isToday = time.toDateString() === new Date().toDateString()

  function formatFov(f) {
    if (f >= 1) return `${parseFloat(f.toPrecision(2))}°`
    return `${parseFloat((f * 60).toPrecision(2))}′`
  }

  function formatMag(m) {
    return m.toFixed(1)
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
    if (String(obj?.id || '').startsWith('star_t2_')) return 'Unnamed'
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
    if (id.startsWith('star_t2_')) return 'Unnamed'
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

  function dblPairs(obj, ds) {
    if (obj.type === 'double_star') return obj.pairs || []
    if (Array.isArray(obj.dbl)) return obj.dbl.flatMap((e) => e.pairs || [])
    if (obj.dbl && ds) return ds.pairs || []
    return []
  }

  function dblMainPair(obj, ds) {
    const pairs = dblPairs(obj, ds)
    return pairs.find((p) => p.comp === 'AB') || pairs[0] || null
  }

  function formatSep(sep) {
    if (sep == null) return null
    if (Array.isArray(sep)) return `${sep[0]}″–${sep[1]}″`
    return `${sep}″`
  }

  function dsoSizeStr(obj) {
    const s = obj.size
    if (s == null) return null
    const major = Array.isArray(s) ? s[0] : s
    const fmt = (arcmin) => {
      if (major < 1) return `${Math.round(arcmin * 60)}″`
      if (major < 60) return `${arcmin.toFixed(1)}′`
      return `${(arcmin / 60).toFixed(2)}°`
    }
    if (Array.isArray(s)) return `${fmt(s[0])}×${fmt(s[1])}`
    return fmt(s)
  }

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }

  function selectedObjLabel(obj, ds) {
    if (!obj) return ''
    const isDoubleObj = obj.type === 'double_star' || (obj.type === 'star' && !!obj.dbl)
    if (isDoubleObj) {
      const name = preferredStarLabel(obj)
      const pair = dblMainPair(obj, ds)
      const parts = []
      const sep = pair ? formatSep(pair.sep) : null
      if (sep != null) parts.push(`sep. ${sep}`)
      if (pair?.mag && Array.isArray(pair.mag)) parts.push(`mag. ${pair.mag[0]}/${pair.mag[1]}`)
      return esc(parts.length ? `${name} (${parts.join(', ')})` : name)
    }
    if (obj.type === 'star') {
      const name = preferredStarLabel(obj)
      if (Array.isArray(obj.mag)) return esc(`${name} (mag. ${obj.mag[0]}–${obj.mag[1]})`)
      if (obj.mag != null) return esc(`${name} (mag. ${obj.mag})`)
      return esc(name)
    }
    if (obj.type === 'dso') {
      const catLabel = primaryCatalogueLabel(obj)
      const rawName = String(obj.name || '').trim()
      const normalizedName = rawName
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .join(', ')
      const hasName = normalizedName && normalizedName.toLowerCase() !== catLabel.toLowerCase()
      const sizeStr = dsoSizeStr(obj)
      const magStr = obj.mag != null ? `mag. ${Array.isArray(obj.mag) ? obj.mag[0] : obj.mag}` : null
      const parts = [sizeStr, magStr].filter(Boolean)
      const detail = parts.length ? esc(` (${parts.join(', ')})`) : ''
      return hasName
        ? `<strong>${esc(catLabel)}</strong> ${esc(normalizedName)}${detail}`
        : `<strong>${esc(catLabel)}</strong>${detail}`
    }
    return esc(objLabel(obj))
  }
</script>

<div class="top-bar" on:pointerdown|stopPropagation>
  <div class="row1">
    <div class="left-group">
      <button class="datetime-btn" on:click={() => dispatch('timepick')}>
        {#if isToday}
          <span class="dt-time">{formatTime(time)}</span>
        {:else}
          <span class="dt-date">{formatDate(time)}</span>
        {/if}
      </button>
      {#if batteryLevel !== null}
        <span class="batt-group">
          <svg class="batt-icon" width="18" height="10" viewBox="0 0 18 10">
            <rect x="0.5" y="0.5" width="14" height="9" rx="2" stroke="currentColor" stroke-width="1" fill="none" />
            <rect x="14.5" y="2.5" width="2.5" height="5" rx="1" fill="currentColor" />
            <rect x="1.5" y="1.5" width={battFillW(batteryLevel)} height="7" rx="1" fill="currentColor" />
          </svg>
          <span class="batt-pct">{batteryLevel}%</span>
        </span>
      {/if}
    </div>

    <div class="center-group">
      <button
        class="toggle-btn"
        class:active={$searchViewActive}
        on:click={() => dispatch('searchtoggle')}
        aria-label="Search"
      >
        <SearchIcon />
      </button>
      <button
        class="toggle-btn"
        class:active={$finderViewActive}
        on:click={() => finderViewActive.update((v) => !v)}
        aria-label="Finder view"
      >
        <FinderViewIcon />
      </button>
      <button class="toggle-btn" class:active={$theme === 'nightly'} on:click={toggleTheme} aria-label="Night mode">
        <NightModeIcon />
      </button>
      <button class="menu-btn" on:click={() => dispatch('menutoggle')} aria-label="Menu">
        <HamburgerIcon />
      </button>
      {#if fullscreenSupported && !isFullscreen}
        <button class="toggle-btn fs-btn" on:click={enterFullscreen} aria-label="Enter fullscreen">
          <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
            <path
              d="M1 5V1h4M10 1h4v4M14 10v4h-4M5 14H1v-4"
              stroke="currentColor"
              stroke-width="1.4"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </button>
      {/if}
    </div>

    <div class="right-info">
      {#if fov != null}
        <span>{formatFov(fov)}</span>
      {/if}
      {#if magMin != null && magMax != null}
        <span>, m. {formatMag(magMin)}–{formatMag(magMax)}</span>
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
      <!-- eslint-disable-next-line svelte/no-at-html-tags -->
      <span class="obj-name">{@html selectedObjLabel($selectedObject, linkedDs)}</span>
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
    color: var(--surface-fg);
    pointer-events: none;
  }

  .row1 {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    height: 2.75rem;
    padding: 0 0.6rem;
    background: var(--surface-bg);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    pointer-events: auto;
  }

  .left-group {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .datetime-btn {
    background: none;
    border: none;
    color: inherit;
    padding: 0;
    display: flex;
    align-items: baseline;
    font-size: 0.82rem;
    cursor: pointer;
    text-align: left;
  }

  .dt-date {
    opacity: 0.6;
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

  .toggle-btn {
    background: none;
    border: none;
    color: inherit;
    padding: 0.4rem 0.5rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0.45;
  }

  .toggle-btn.active,
  .toggle-btn:hover {
    opacity: 1;
  }

  .fs-btn {
    opacity: 0.55;
  }

  .batt-group {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    opacity: 0.7;
  }

  .batt-icon {
    flex-shrink: 0;
  }

  .batt-pct {
    font-size: 0.7rem;
    line-height: 1;
  }

  .right-info {
    display: flex;
    align-items: baseline;
    justify-content: flex-end;
    font-size: 0.78rem;
    opacity: 0.7;
    white-space: nowrap;
  }

  .row2 {
    display: inline-flex;
    align-items: center;
    gap: 0.1rem;
    height: 2rem;
    padding: 0 0.6rem 0 0.35rem;
    background: var(--surface-bg);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-radius: 0 0 8px 0;
    font-size: 0.82rem;
    cursor: pointer;
    pointer-events: auto;
    max-width: calc(100vw - 1rem);
  }

  .row2:hover {
    background: var(--surface-bg);
    filter: brightness(1.08);
  }

  .obj-icon {
    font-size: 0.85rem;
    opacity: 0.75;
    flex-shrink: 0;
    margin-right: 0.25rem;
  }
  .obj-name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .obj-name :global(strong) {
    font-weight: 600;
  }
</style>
