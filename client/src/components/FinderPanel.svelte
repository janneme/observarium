<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import SkyCanvas from './SkyCanvas.svelte'
  import CustomInput from './CustomInput.svelte'
  import OnScreenKeyboard from './OnScreenKeyboard.svelte'
  import { selectedObject } from '../stores/selectedObject.js'
  import { finderViewActive, searchViewActive, pendingFocus } from '../stores/ui.js'
  import { getMeta, getObjectsInArea, getSearchIndex } from '../lib/db.js'
  import { get } from 'svelte/store'

  export let mainRa0 = 0
  export let mainDec0 = 0
  export let lat = 48.2
  export let lon = 16.37
  export let time = new Date()

  const FINDER_FOV = 7.5
  const EUROPE_MIN_DEC = -35
  let wrapEl
  let finderRa0 = mainRa0
  let finderDec0 = mainDec0
  let objects = []
  let hasPath = false
  const pointers = new Map()

  let prevObjId = undefined
  $: {
    const obj = $selectedObject
    const id = obj?.id ?? null
    if (id !== prevObjId) {
      prevObjId = id
      if (obj?.pos) {
        finderRa0 = obj.pos[0]
        finderDec0 = obj.pos[1]
      }
      void loadObjects()
      void checkPath()
    }
  }

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
      return
    }
    try {
      const paths = await getMeta('findingPaths')
      hasPath = !!(paths && paths[obj.id] && Object.keys(paths[obj.id]).length > 0)
    } catch {
      hasPath = false
    }
  }

  function applyPan(dx, dy, raC, decC, sizePx) {
    const fovRad = (FINDER_FOV * Math.PI) / 180
    const scale = sizePx / fovRad
    const x = -dx / scale
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
    if (searching) {
      if (e.key === 'Escape') {
        closeSearch()
        e.preventDefault()
        e.stopPropagation()
      }
      return
    }
    if (get(searchViewActive)) return
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

  onMount(() => window.addEventListener('keydown', handleKey, true))
  onDestroy(() => window.removeEventListener('keydown', handleKey, true))

  function switchToMain() {
    finderViewActive.set(false)
  }

  function stub(label) {
    console.log('[FinderPanel] stub:', label)
  }
</script>

<div class="finder-overlay" on:pointerdown={(e) => e.stopPropagation()}>
  <div class="circle-container">
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
            placeholder="Search objects…"
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
      <button class="finder-btn" on:click={openSearch}>Search object</button>
      {#if hasPath}
        <button class="finder-btn" on:click={() => stub('guide')}>Guide to find the object</button>
      {/if}
      <button class="finder-btn" on:click={() => stub('record')}>Record guide to find object</button>
    </div>
  {/if}
</div>

<style>
  .finder-overlay {
    position: fixed;
    inset: 0;
    z-index: 100;
    background: #0a0a0a;
    display: flex;
    flex-direction: column;
    user-select: none;
  }

  .circle-container {
    flex-shrink: 0;
    position: relative;
    width: calc(100vw - 2vh);
    aspect-ratio: 1;
    margin: 1vh 1vh 0;
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

  .finder-btn {
    width: 100%;
    padding: 1.7vh 2vh;
    background: rgba(255, 255, 255, 0.07);
    color: var(--surface-fg, #fff);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 1.2vh;
    font-size: 1.8vh;
    font-family: inherit;
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

  :global([data-theme='nightly']) .circle-container::after {
    border-color: rgba(180, 0, 0, 0.3);
  }

  :global([data-theme='nightly']) .finder-btn {
    color: #ff8080;
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
    background: #0a0a0a;
    color: #e0e0e0;
    --fg: #e0e0e0;
    --bg: #0a0a0a;
    --key-bg: rgba(255, 255, 255, 0.08);
  }

  .fs-bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .fs-input-wrap {
    flex: 1;
    min-width: 0;
    font-size: 1rem;
    color: #e0e0e0;
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
  }

  .fs-results {
    flex: 1;
    overflow-y: auto;
    overscroll-behavior: contain;
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
    padding: 0.6rem 0.75rem;
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

  :global([data-theme='nightly']) .fs-result-row:active {
    background: rgba(180, 0, 0, 0.1);
  }
</style>
