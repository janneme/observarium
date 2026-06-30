<script>
  import { createEventDispatcher, onMount, onDestroy, tick } from 'svelte'
  import SkyCanvas from './SkyCanvas.svelte'
  import CustomInput from './CustomInput.svelte'
  import OnScreenKeyboard from './OnScreenKeyboard.svelte'
  import ObservationObjectSymbol from './ObservationObjectSymbol.svelte'
  import { selectedObject } from '../stores/selectedObject.js'
  import { finderViewActive, searchViewActive, pendingFocus } from '../stores/ui.js'
  import { getMeta, getObjectsInArea, getSearchIndex } from '../lib/db.js'
  import { get } from 'svelte/store'

  const dispatch = createEventDispatcher()

  export let mainRa0 = 0
  export let mainDec0 = 0
  export let lat = 48.2
  export let lon = 16.37
  export let time = new Date()
  export let pathStateVersion = 0

  const FINDER_FOV = 7.5
  const EUROPE_MIN_DEC = -35
  const LABEL_TOP_REM = 0.35
  const LABEL_ICON_BLOCK_REM = 1.3
  const LABEL_LINE_HEIGHT_REM = 1
  const LABEL_LINES = 2
  const LABEL_MIN_WIDTH_PX = 88
  let wrapEl
  let circleEl
  let finderRa0 = mainRa0
  let finderDec0 = mainDec0
  let objects = []
  let hasPath = false
  let rawPaths = {}
  let pathCheckNonce = 0
  let guidePickerOpen = false
  let guideOptions = []
  let labelBoxWidthPx = 120
  const pointers = new Map()

  let prevObjId = undefined
  $: {
    const obj = $selectedObject
    const id = obj?.id ?? null
    if (id !== prevObjId) {
      prevObjId = id
      hasPath = false
      rawPaths = {}
      guidePickerOpen = false
      if (obj?.pos) {
        finderRa0 = obj.pos[0]
        finderDec0 = obj.pos[1]
      }
      void loadObjects()
      void checkPath()
    }
  }

  // Refresh path availability when path data changes externally for the same selected object.
  $: {
    pathStateVersion
    hasPath = false
    void checkPath()
  }

  $: pathCount = Object.values(rawPaths).filter(
    (p) => Array.isArray(p?.steps) && p.steps.length > 0 && p.steps[p.steps.length - 1]?.final === true,
  ).length

  async function loadObjects() {
    const margin = FINDER_FOV * 2
    objects = await getObjectsInArea(
      finderRa0 - margin,
      finderRa0 + margin,
      finderDec0 - margin,
      finderDec0 + margin,
      12,
    )
  }

  async function checkPath() {
    const obj = $selectedObject
    if (!obj) {
      hasPath = false
      rawPaths = {}
      return
    }
    const checkId = obj.id
    const nonce = ++pathCheckNonce
    try {
      const paths = await getMeta('findingPaths')
      if (nonce !== pathCheckNonce) return
      const byStart = paths && paths[checkId]
      const candidate = byStart && typeof byStart === 'object' ? byStart : {}
      rawPaths = candidate
      hasPath = Object.values(candidate).some(
        (p) => Array.isArray(p?.steps) && p.steps.length > 0 && p.steps[p.steps.length - 1]?.final === true,
      )
    } catch {
      if (nonce !== pathCheckNonce) return
      hasPath = false
      rawPaths = {}
    }
  }

  function applyPan(dx, dy, raC, decC, sizePx) {
    const fovRad = (FINDER_FOV * Math.PI) / 180
    const scale = sizePx / fovRad
    const x = dx / scale
    const y = dy / scale
    const rho = Math.sqrt(x * x + y * y)
    if (rho < 1e-10) return { ra0: raC, dec0: decC }
    const dec0_r = (decC * Math.PI) / 180
    const c = Math.atan(rho)
    const sinC = Math.sin(c),
      cosC = Math.cos(c)
    const dec_r = Math.asin(Math.max(-1, Math.min(1, cosC * Math.sin(dec0_r) + (y * sinC * Math.cos(dec0_r)) / rho)))
    const ra_r =
      (raC * Math.PI) / 180 + Math.atan2(x * sinC, rho * Math.cos(dec0_r) * cosC - y * Math.sin(dec0_r) * sinC)
    const decMin = EUROPE_MIN_DEC + FINDER_FOV / 2
    return {
      ra0: ((((ra_r * 180) / Math.PI) % 360) + 360) % 360,
      dec0: Math.max(decMin, Math.min(90, (dec_r * 180) / Math.PI)),
    }
  }

  function handlePointerDown(e) {
    e.preventDefault()
    wrapEl.setPointerCapture(e.pointerId)
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
  }

  function handlePointerMove(e) {
    if (!pointers.has(e.pointerId)) return
    const prev = pointers.get(e.pointerId)
    if (pointers.size === 1) {
      const rect = wrapEl.getBoundingClientRect()
      if (rect.width > 0) {
        const result = applyPan(e.clientX - prev.x, e.clientY - prev.y, finderRa0, finderDec0, rect.width)
        finderRa0 = result.ra0
        finderDec0 = result.dec0
      }
    }
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
  }

  function handlePointerUp(e) {
    pointers.delete(e.pointerId)
    if (pointers.size === 0) void loadObjects()
  }

  function handlePointerCancel(e) {
    pointers.delete(e.pointerId)
  }

  // ── Inline search state ──────────────────────────────────────
  let searching = false
  let searchQuery = ''
  let searchResults = []
  let searchIndex = null
  let searchLoading = false
  let searchInputComp

  function normQuery(s) {
    return s.trim().toLowerCase().replace(/\s+/g, '')
  }

  function catEntries(obj) {
    const cats = []
    if (obj.m != null) {
      const n = String(obj.m)
      cats.push({ label: `M${obj.m}`, tokens: [`m${n}`, n] })
    }
    if (obj.ngc != null) {
      const n = String(obj.ngc)
      cats.push({ label: `NGC ${obj.ngc}`, tokens: [`ngc${n}`, n] })
    }
    if (obj.ic != null) {
      const n = String(obj.ic)
      cats.push({ label: `IC ${obj.ic}`, tokens: [`ic${n}`, n] })
    }
    if (obj.caldwell != null) {
      const n = String(obj.caldwell)
      cats.push({ label: `C ${obj.caldwell}`, tokens: [`c${n}`, `caldwell${n}`] })
    }
    if (obj.hip != null) {
      cats.push({ label: `HIP ${obj.hip}`, tokens: [`hip${String(obj.hip)}`] })
    }
    if (obj.hd != null) {
      cats.push({ label: `HD ${obj.hd}`, tokens: [`hd${String(obj.hd)}`] })
    }
    return cats
  }

  function doSearch(q) {
    if (!searchIndex) return []
    const nq = normQuery(q)
    if (!nq) return []
    const out = [],
      seen = new Set()
    function add(obj, display) {
      if (seen.has(obj.id)) return
      seen.add(obj.id)
      out.push({ obj, display, con: obj.constellation || null })
    }
    for (const obj of searchIndex) {
      if (obj.name && obj.name.toLowerCase().startsWith(nq)) add(obj, obj.name)
    }
    for (const obj of searchIndex) {
      if (seen.has(obj.id)) continue
      for (const cat of catEntries(obj)) {
        if (cat.tokens.some((t) => t.startsWith(nq))) {
          add(obj, cat.label)
          break
        }
      }
    }
    for (const obj of searchIndex) {
      if (!seen.has(obj.id) && obj.name && obj.name.toLowerCase().includes(nq)) add(obj, obj.name)
    }
    return out.slice(0, 20)
  }

  $: searchResults = doSearch(searchQuery)

  async function openSearch() {
    searching = true
    searchQuery = ''
    if (!searchIndex) {
      searchLoading = true
      searchIndex = await getSearchIndex()
      searchLoading = false
    }
    await tick()
    searchInputComp?.focus()
  }

  function closeSearch() {
    searching = false
    searchQuery = ''
  }

  function acceptResult(item) {
    selectedObject.set(item.obj)
    if (item.obj.pos) pendingFocus.set({ ra: item.obj.pos[0], dec: item.obj.pos[1] })
    closeSearch()
  }
  // ─────────────────────────────────────────────────────────────

  function handleKey(e) {
    if (guidePickerOpen) {
      if (e.key === 'Escape') {
        guidePickerOpen = false
        e.preventDefault()
        e.stopPropagation()
        return
      }
      if (e.key.length === 1) {
        const match = guideOptions.find((opt) => opt.label.toLowerCase().startsWith(e.key.toLowerCase()))
        if (match) pickGuide(match.startHip)
        e.preventDefault()
        e.stopPropagation()
      }
      return
    }

    if (searching) {
      if (e.key === 'Escape') {
        closeSearch()
        e.preventDefault()
        e.stopPropagation()
      }
      return
    }
    if (get(searchViewActive)) return

    if (e.key === 'f') {
      openSearch()
      e.preventDefault()
      e.stopPropagation()
      return
    }

    if (e.key === 'a') {
      if ($selectedObject) recordPath()
      e.preventDefault()
      e.stopPropagation()
      return
    }

    if (e.key === 'p') {
      if ($selectedObject && hasPath) openGuidePicker()
      e.preventDefault()
      e.stopPropagation()
      return
    }

    const decMin = EUROPE_MIN_DEC + FINDER_FOV / 2
    const step = FINDER_FOV / 3
    if (e.key === 'ArrowRight') {
      finderRa0 = (((finderRa0 + step / Math.max(0.1, Math.cos((finderDec0 * Math.PI) / 180))) % 360) + 360) % 360
    } else if (e.key === 'ArrowLeft') {
      finderRa0 = (((finderRa0 - step / Math.max(0.1, Math.cos((finderDec0 * Math.PI) / 180))) % 360) + 360) % 360
    } else if (e.key === 'ArrowUp') {
      finderDec0 = Math.min(90, finderDec0 + step)
    } else if (e.key === 'ArrowDown') {
      finderDec0 = Math.max(decMin, finderDec0 - step)
    } else {
      return
    }
    e.preventDefault()
    e.stopPropagation()
    void loadObjects()
  }

  function updateLabelGeometry() {
    if (!circleEl) return
    const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
    const size = circleEl.getBoundingClientRect().width
    if (!(size > 0)) return
    const r = size / 2
    const topPx = LABEL_TOP_REM * rootPx
    const contentHeightPx = Math.max(LABEL_ICON_BLOCK_REM * rootPx, LABEL_LINE_HEIGHT_REM * rootPx * LABEL_LINES)
    const yBottom = topPx + contentHeightPx
    const dy = yBottom - r
    const xBoundary = r - Math.sqrt(Math.max(0, r * r - dy * dy))
    const maxWidth = xBoundary - topPx
    labelBoxWidthPx = Math.max(LABEL_MIN_WIDTH_PX, Math.floor(maxWidth))
  }

  onMount(() => {
    window.addEventListener('keydown', handleKey, true)
    window.addEventListener('resize', updateLabelGeometry)
    setTimeout(updateLabelGeometry, 0)
  })

  onDestroy(() => {
    window.removeEventListener('keydown', handleKey, true)
    window.removeEventListener('resize', updateLabelGeometry)
  })

  $: if ($selectedObject) {
    setTimeout(updateLabelGeometry, 0)
  }

  function switchToMain() {
    finderViewActive.set(false)
  }

  function recordPath() {
    if (!$selectedObject) return
    dispatch('recordpath', { object: $selectedObject })
  }

  async function openGuidePicker() {
    if (!$selectedObject || !hasPath) return
    if (!searchIndex) {
      searchIndex = await getSearchIndex()
    }
    const hipLabels = new Map()
    for (const obj of searchIndex) {
      if (obj.hip != null && (obj.type === 'star' || obj.type === 'double_star')) {
        const key = String(obj.hip)
        if (!hipLabels.has(key)) hipLabels.set(key, preferredStarLabel(obj))
      }
    }
    guideOptions = Object.entries(rawPaths)
      .filter(([, p]) => Array.isArray(p?.steps) && p.steps.length > 0 && p.steps[p.steps.length - 1]?.final === true)
      .map(([startHip, path]) => ({
        startHip,
        label: hipLabels.get(String(startHip)) || `HIP ${startHip}`,
        stepCount: path.steps.length,
      }))
      .sort((a, b) => a.label.localeCompare(b.label))
    guidePickerOpen = true
  }

  function pickGuide(startHip) {
    guidePickerOpen = false
    dispatch('guidepath', { object: $selectedObject, startHip })
  }

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

  function selectedObjectLabel(obj) {
    if (!obj) return ''
    if (obj.type === 'star') return preferredStarLabel(obj)
    const catalogue = primaryCatalogueLabel(obj)
    const rawName = String(obj.name || '').trim()
    if (!rawName) return catalogue
    if (rawName.toLowerCase() === String(catalogue).toLowerCase()) return catalogue
    return `${catalogue} (${rawName})`
  }
</script>

<div class="finder-overlay" on:pointerdown={(e) => e.stopPropagation()}>
  <div class="circle-container">
    <div class="circle-anchor" bind:this={circleEl}></div>
    {#if $selectedObject}
      <div class="finder-object-box" style={`width:${labelBoxWidthPx}px`} on:pointerdown|stopPropagation>
        <span class="box-icon"><ObservationObjectSymbol kind={objectSymbolKind($selectedObject)} /></span>
        <span class="box-text">{selectedObjectLabel($selectedObject)}</span>
      </div>
    {/if}

    <div
      class="circle-wrap"
      bind:this={wrapEl}
      on:pointerdown={handlePointerDown}
      on:pointermove={handlePointerMove}
      on:pointerup={handlePointerUp}
      on:pointercancel={handlePointerCancel}
    >
      <SkyCanvas
        ra0={finderRa0}
        dec0={finderDec0}
        fov={FINDER_FOV}
        {objects}
        {lat}
        {lon}
        {time}
        finderMode={true}
        showFovCircle={false}
        showConstellationLines={false}
        showConstellationNames={false}
        showConstellationBoundaries={false}
        showDsos={true}
        showHorizon={true}
        showSolarSystem={true}
      />
    </div>
  </div>

  {#if searching}
    <div class="finder-search" on:pointerdown|stopPropagation>
      <div class="fs-bar">
        <div class="fs-input-wrap">
          <CustomInput
            bind:this={searchInputComp}
            bind:value={searchQuery}
            placeholder="Search"
            on:enter={() => searchResults[0] && acceptResult(searchResults[0])}
          />
        </div>
        <button class="fs-cancel" on:click={closeSearch}>Cancel</button>
      </div>
      <div class="fs-keyboard">
        <OnScreenKeyboard />
      </div>
      <div class="fs-results">
        {#if searchLoading}
          <div class="fs-hint">Loading…</div>
        {:else if !searchQuery}
          <div class="fs-hint">Type to search</div>
        {:else if searchResults.length === 0}
          <div class="fs-hint">No results</div>
        {:else}
          {#each searchResults as item (item.obj.id)}
            <div
              class="fs-result-row"
              role="button"
              tabindex="0"
              on:click={() => acceptResult(item)}
              on:keydown={(e) => e.key === 'Enter' && acceptResult(item)}
            >
              <span class="fs-result-label">{item.display}{item.con ? ` (${item.con})` : ''}</span>
            </div>
          {/each}
        {/if}
      </div>
    </div>
  {:else}
    <div class="scroll-area">
      <button class="finder-btn" on:click={switchToMain}>Switch to normal view</button>
      <button class="finder-btn" on:click={openSearch}>Find object</button>
      {#if hasPath}
        <button class="finder-btn" on:click={openGuidePicker}
          >Paths{' '}<span class="guide-btn-count">({pathCount})</span></button
        >
      {/if}
      {#if $selectedObject}
        <button class="finder-btn" on:click={recordPath}>Add finding path</button>
      {/if}
    </div>
  {/if}

  {#if guidePickerOpen}
    <div class="guide-picker-backdrop" on:click={() => (guidePickerOpen = false)} aria-hidden="true" />
    <div class="guide-picker-modal" role="dialog" aria-modal="true">
      <div class="guide-pick-title">Choose start star</div>
      <div class="guide-picker-list">
        {#each guideOptions as opt}
          <button class="finder-btn" on:click={() => pickGuide(opt.startHip)}>
            <strong>{opt.label}</strong>{' '}<span class="opt-steps"
              >({opt.stepCount} {opt.stepCount === 1 ? 'step' : 'steps'})</span
            >
          </button>
        {/each}
      </div>
      <button class="finder-btn guide-cancel-btn" on:click={() => (guidePickerOpen = false)}>Cancel</button>
    </div>
  {/if}
</div>

<style>
  .finder-overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 9;
    background: #0a0a0a;
    display: flex;
    flex-direction: column;
    user-select: none;
    color: var(--fg);
  }

  .circle-container {
    flex-shrink: 0;
    position: relative;
    width: calc(100vw - 2vh);
    aspect-ratio: 1;
    margin: 1vh 1vh 0;
  }

  .circle-anchor {
    position: absolute;
    inset: 0;
  }

  .circle-container::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 1px solid rgba(255, 255, 255, 0.25);
    pointer-events: none;
    z-index: 1;
    box-sizing: border-box;
  }

  .circle-wrap {
    position: absolute;
    inset: 0;
    clip-path: circle(50%);
    touch-action: none;
    cursor: grab;
  }

  .finder-object-box {
    position: absolute;
    top: 0.35rem;
    left: 0.35rem;
    z-index: 2;
    display: flex;
    align-items: flex-start;
    gap: 0.3rem;
    padding: 0;
  }

  .box-icon {
    flex-shrink: 0;
    margin-top: 0.04rem;
    opacity: 0.9;
  }

  .box-text {
    font-size: 0.72rem;
    line-height: 1rem;
    color: var(--fg);
    white-space: normal;
    overflow: hidden;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    line-clamp: 2;
    -webkit-line-clamp: 2;
  }

  .circle-wrap:active {
    cursor: grabbing;
  }

  .scroll-area {
    flex: 1;
    overflow-y: auto;
    padding: 1vh 2vh 3vh;
    display: flex;
    flex-direction: column;
    gap: 1.2vh;
  }

  .guide-picker-backdrop {
    position: fixed;
    inset: 0;
    z-index: 20;
    background: rgba(0, 0, 0, 0.6);
  }

  .guide-picker-modal {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 21;
    background: #141414;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 1.8vh;
    padding: 2.5vh 2.5vh 2vh;
    width: min(88vw, 36vh);
    display: flex;
    flex-direction: column;
    gap: 1.2vh;
  }

  .guide-pick-title {
    font-size: 1.6vh;
    color: rgba(255, 255, 255, 0.6);
    text-align: center;
    padding: 0 0 0.4vh;
  }

  .guide-picker-list {
    display: flex;
    flex-direction: column;
    gap: 1vh;
    max-height: 40vh;
    overflow-y: auto;
  }

  .guide-cancel-btn {
    margin-top: 0.4vh;
  }

  .opt-steps {
    font-weight: normal;
  }

  .guide-btn-count {
    font-weight: normal;
  }

  .finder-btn {
    width: 100%;
    padding: 1.7vh 2vh;
    background: rgba(255, 255, 255, 0.07);
    color: var(--fg);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 1.2vh;
    font-size: 1.8vh;
    font-family: inherit;
    font-weight: 600;
    text-align: center;
    cursor: pointer;
    transition: background 150ms;
    flex-shrink: 0;
  }

  .finder-btn:hover,
  .finder-btn:focus-visible {
    background: rgba(255, 255, 255, 0.13);
    outline: none;
  }

  :global([data-theme='nightly']) .finder-overlay {
    background: #110000;
  }

  :global([data-theme='nightly']) .guide-picker-backdrop {
    background: rgba(40, 0, 0, 0.7);
  }

  :global([data-theme='nightly']) .guide-picker-modal {
    background: #1a0000;
    border-color: rgba(180, 0, 0, 0.25);
  }

  :global([data-theme='nightly']) .guide-pick-title {
    color: #ff0000;
  }

  :global([data-theme='nightly']) .circle-container::after {
    border-color: rgba(180, 0, 0, 0.3);
  }

  :global([data-theme='nightly']) .finder-btn {
    color: #ff0000;
    border-color: rgba(180, 0, 0, 0.25);
    background: rgba(180, 0, 0, 0.08);
  }

  :global([data-theme='nightly']) .finder-btn:hover {
    background: rgba(180, 0, 0, 0.14);
  }

  /* ── Inline finder search ── */
  .finder-search {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    margin-top: -16vh;
    background: #0a0a0a;
    color: #e0e0e0;
    --fg: #e0e0e0;
    --bg: #0a0a0a;
    --key-bg: rgba(255, 255, 255, 0.08);
    position: relative;
    z-index: 1;
  }

  .fs-bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.45rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .fs-input-wrap {
    flex: 1;
    min-width: 0;
    font-size: 1rem;
    color: var(--fg);
  }

  .fs-input-wrap :global(.custom-input) {
    border-color: rgba(255, 255, 255, 0.18);
  }

  .fs-cancel {
    flex-shrink: 0;
    background: none;
    border: none;
    color: #7aafff;
    font-size: 0.95rem;
    padding: 0.35rem 0.5rem;
    cursor: pointer;
    border-radius: 4px;
    font-family: inherit;
  }

  .fs-cancel:hover {
    background: rgba(255, 255, 255, 0.1);
  }

  .fs-keyboard {
    flex-shrink: 0;
    margin-bottom: 0.5rem;
  }

  .fs-results {
    flex: 1;
    overflow-y: auto;
    overscroll-behavior: contain;
    background: rgba(0, 0, 0, 0.3);
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }

  .fs-hint {
    padding: 1rem;
    text-align: center;
    color: rgba(255, 255, 255, 0.35);
    font-size: 0.88rem;
  }

  .fs-result-row {
    display: flex;
    align-items: center;
    padding: 0.9rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    cursor: pointer;
  }

  .fs-result-row:active {
    background: rgba(255, 255, 255, 0.07);
  }

  .fs-result-label {
    flex: 1;
    font-size: 0.88rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Nightly overrides for inline search */
  :global([data-theme='nightly']) .finder-search {
    background: #110000;
    color: #cc0000;
    --fg: #cc0000;
    --bg: #110000;
    --key-bg: rgba(80, 0, 0, 0.55);
  }

  :global([data-theme='nightly']) .finder-search :global(.placeholder) {
    opacity: 0.75;
  }

  :global([data-theme='nightly']) .fs-bar {
    border-bottom-color: rgba(180, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .fs-input-wrap :global(.custom-input) {
    border-color: rgba(180, 0, 0, 0.3);
  }

  :global([data-theme='nightly']) .fs-cancel {
    color: #cc0000;
  }

  :global([data-theme='nightly']) .fs-cancel:hover {
    background: rgba(180, 0, 0, 0.15);
  }

  :global([data-theme='nightly']) .fs-hint {
    color: rgba(200, 0, 0, 0.5);
  }

  :global([data-theme='nightly']) .fs-result-row {
    border-bottom-color: rgba(180, 0, 0, 0.15);
  }

  :global([data-theme='nightly']) .fs-results {
    border-top-color: rgba(180, 0, 0, 0.2);
    background: rgba(40, 0, 0, 0.24);
  }

  :global([data-theme='nightly']) .fs-result-row:active {
    background: rgba(180, 0, 0, 0.1);
  }
</style>
