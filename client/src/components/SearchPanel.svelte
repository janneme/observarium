<script>
  import { createEventDispatcher, onMount, onDestroy, tick } from 'svelte'
  import CustomInput from './CustomInput.svelte'
  import OnScreenKeyboard from './OnScreenKeyboard.svelte'
  import { clearTarget } from '../stores/keyboard.js'
  import { selectedObject } from '../stores/selectedObject.js'
  import { searchViewActive, objectDetailsActive, pendingFocus, solarSystemPositions } from '../stores/ui.js'
  import { doSearch } from '../lib/search.js'
  import { getSearchIndex, getObjectIdsWithFindingPaths } from '../lib/db.js'
  import FindingPathsIcon from '../icons/FindingPathsIcon.svelte'
  import InfoIcon from '../icons/InfoIcon.svelte'

  const dispatch = createEventDispatcher()

  export let placeholder = 'Search objects…'
  export let emptyHint = 'Type to search'
  export let noResultsHint = 'No results'
  export let useSearchStore = true
  export let manageSelection = true
  export let includeSolar = true
  export let showDetailsAction = true
  export let showFindingPathsAction = true
  export let autoCloseOnAccept = true
  export let topOffset = '2.75rem'
  export let zIndex = 9
  export let resultFilter = null
  export let onAcceptObject = null
  export let title = null

  let query = ''
  let results = []
  let index = null
  let loading = true
  let inputComp
  let objectIdsWithPaths = new Set()

  function onKey(e) {
    if (e.key === 'Escape') close()
  }

  onMount(async () => {
    window.addEventListener('keydown', onKey)
    await tick()
    inputComp?.focus()
    ;[index, objectIdsWithPaths] = await Promise.all([getSearchIndex(), getObjectIdsWithFindingPaths()])
    loading = false
  })

  onDestroy(() => {
    window.removeEventListener('keydown', onKey)
    clearTarget()
  })

  function close() {
    clearTarget()
    if (useSearchStore) searchViewActive.set(false)
    dispatch('close')
  }

  $: solarEntries = includeSolar
    ? $solarSystemPositions.map((b) => ({
        id: `solar_${b.imageId || b.name.toLowerCase()}`,
        name: b.name,
        pos: [b.ra, b.dec],
        type: 'solar_system_body',
        bodyClass: b.bodyClass,
      }))
    : []

  $: rawResults = doSearch(query, index ? [...solarEntries, ...index] : solarEntries.length ? solarEntries : null)

  $: results =
    typeof resultFilter === 'function'
      ? rawResults.filter((item) => {
          try {
            return !!resultFilter(item.obj)
          } catch {
            return false
          }
        })
      : rawResults

  async function accept(item) {
    if (typeof onAcceptObject === 'function') {
      const shouldContinue = await onAcceptObject(item.obj, item)
      if (shouldContinue === false) return
    }
    dispatch('accept', { object: item.obj, item })
    if (manageSelection) {
      selectedObject.set(item.obj)
      if (item.obj.pos) pendingFocus.set({ ra: item.obj.pos[0], dec: item.obj.pos[1] })
    }
    if (autoCloseOnAccept) close()
  }

  function details(item) {
    dispatch('details', { object: item.obj, item })
    if (manageSelection) {
      selectedObject.set(item.obj)
      if (useSearchStore) searchViewActive.set(false)
      objectDetailsActive.set(true)
    }
  }

  function findingPaths(item) {
    dispatch('findingpaths', { object: item.obj })
  }

  function splitDsoLabel(display) {
    const raw = String(display || '')
    const cut = raw.indexOf(' – ')
    if (cut < 0) return null
    return {
      left: raw.slice(0, cut),
      right: raw.slice(cut + 3),
    }
  }

  function splitCatalogAndConst(leftPart) {
    const raw = String(leftPart || '').trim()
    if (!raw) return { cat: '', constSuffix: '' }
    const m = raw.match(/^(.*?)(\s*\([^)]+\))$/)
    if (!m) return { cat: raw, constSuffix: '' }
    return {
      cat: m[1].trim(),
      constSuffix: m[2],
    }
  }
</script>

<div class="search-overlay" style={`top:${topOffset}; z-index:${zIndex};`} on:pointerdown|stopPropagation>
  {#if title}
    <div class="search-title">{title}</div>
  {/if}
  <div class="search-bar">
    <div class="input-wrap">
      <CustomInput
        bind:this={inputComp}
        bind:value={query}
        {placeholder}
        on:enter={async () => results[0] && (await accept(results[0]))}
        on:shiftEnter={() => showDetailsAction && results[0] && details(results[0])}
      />
    </div>
    {#if query}
      <button
        class="bar-btn"
        on:click={() => {
          query = ''
        }}
        aria-label="Clear">✕</button
      >
    {/if}
    <button class="bar-btn cancel-btn" on:click={close} aria-label="Close search">←</button>
  </div>

  <div class="kb-area">
    <OnScreenKeyboard />
  </div>

  <div class="results">
    {#if loading}
      <div class="hint">Loading…</div>
    {:else if !query}
      <div class="hint">{emptyHint}</div>
    {:else if results.length === 0}
      <div class="hint">{noResultsHint}</div>
    {:else}
      {#each results as item (item.obj.id)}
        <div
          class="result-row"
          role="button"
          tabindex="0"
          on:click={async () => await accept(item)}
          on:keydown={async (e) => (e.key === 'Enter' || e.key === ' ') && (await accept(item))}
        >
          <span class="result-label">
            {#if item.obj.type === 'dso' && splitDsoLabel(item.display)}
              {@const d = splitDsoLabel(item.display)}
              {@const left = splitCatalogAndConst(d.left)}
              <strong>{left.cat}</strong>{left.constSuffix}
              {' – '}
              <strong>{d.right}</strong>
            {:else if item.obj.type === 'dso'}
              {@const left = splitCatalogAndConst(item.display)}
              <strong>{left.cat}</strong>{left.constSuffix}
            {:else}
              {#each item.spans as span}
                {#if span.hl}<span class="hl">{span.text}</span>{:else}{span.text}{/if}
              {/each}
              {#if item.showCon && item.obj.constellation}
                {' '}({item.obj.constellation})
              {/if}
            {/if}
          </span>
          <div class="result-actions" role="presentation" on:click|stopPropagation on:keydown|stopPropagation>
            {#if showDetailsAction}
              <button class="act-btn details-btn" on:click={() => details(item)} title="Details" aria-label="Details">
                <InfoIcon size="1.2rem" />
              </button>
            {/if}
            {#if showFindingPathsAction && objectIdsWithPaths.has(item.obj.id)}
              <button
                class="act-btn paths-btn"
                on:click={() => findingPaths(item)}
                title="Finding Paths"
                aria-label="Finding Paths"
              >
                <FindingPathsIcon />
              </button>
            {/if}
          </div>
        </div>
      {/each}
    {/if}
  </div>
</div>

<style>
  .search-overlay {
    position: fixed;
    top: 2.75rem; /* below top bar */
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 9; /* below top bar (z-index 10) so bar stays visible */
    background: #0a0a0a;
    display: flex;
    flex-direction: column;
    color: #e0e0e0;
    /* Override theme CSS vars so keyboard keys and caret are visible on dark bg */
    --fg: #e0e0e0;
    --bg: #0a0a0a;
    --key-bg: rgba(255, 255, 255, 0.08);
  }

  .search-title {
    flex-shrink: 0;
    padding: 0.5rem 0.75rem 0.25rem;
    font-size: 0.8rem;
    opacity: 0.6;
    letter-spacing: 0.02em;
  }

  .search-bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .input-wrap {
    flex: 1;
    min-width: 0;
    font-size: 1rem;
    color: #e0e0e0;
  }
  :global([data-theme='nightly']) .input-wrap {
    color: #cc0000;
  }

  .bar-btn {
    flex-shrink: 0;
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.7);
    font-size: 0.95rem;
    padding: 0.35rem 0.5rem;
    cursor: pointer;
    border-radius: 4px;
    transition: background 100ms;
    font-family: inherit;
  }

  .bar-btn:hover {
    background: rgba(255, 255, 255, 0.1);
  }
  .cancel-btn {
    color: #7aafff;
    font-size: 1.2rem;
    padding: 0.25rem 0.45rem;
    line-height: 1;
  }

  .results {
    flex: 1;
    overflow-y: auto;
    overscroll-behavior: contain;
    border-top: 1px solid rgba(255, 255, 255, 0.12);
    margin-top: 0.4rem;
  }

  .hint {
    padding: 1.5rem 1rem;
    text-align: center;
    color: rgba(255, 255, 255, 0.35);
    font-size: 0.9rem;
  }

  .result-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    cursor: pointer;
  }

  .result-row:active {
    background: rgba(255, 255, 255, 0.07);
  }

  .result-label {
    flex: 1;
    min-width: 0;
    font-size: 0.9rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .hl {
    color: #fff;
    font-weight: 600;
  }

  .result-actions {
    flex-shrink: 0;
    display: flex;
    gap: 2px;
  }

  .act-btn {
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.6);
    padding: 0;
    width: 2.2rem;
    height: 2rem;
    overflow: visible;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    cursor: pointer;
    transition: background 100ms;
  }

  .act-btn:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
  }

  .act-btn :global(svg) {
    width: 1.2rem;
    height: 1.2rem;
    min-width: 1.2rem;
    min-height: 1.2rem;
    max-width: 1.2rem;
    max-height: 1.2rem;
    aspect-ratio: 1 / 1;
    flex: 0 0 auto;
    display: block;
  }

  .details-btn :global(svg),
  .paths-btn :global(svg) {
    width: 1.2rem;
    height: 1.2rem;
  }

  /* Make CustomInput border visible on dark background */
  .search-overlay :global(.custom-input) {
    border-color: rgba(255, 255, 255, 0.18);
  }
  :global([data-theme='nightly']) .search-overlay :global(.custom-input) {
    border-color: rgba(255, 100, 100, 0.25);
  }

  /* Nightly theme */
  :global([data-theme='nightly']) .search-overlay {
    background: #110000;
    color: #cc0000;
    --fg: #cc0000;
    --bg: #110000;
    --key-bg: rgba(80, 0, 0, 0.55);
  }
  :global([data-theme='nightly']) .search-bar {
    border-bottom-color: rgba(180, 0, 0, 0.2);
  }
  :global([data-theme='nightly']) .bar-btn {
    color: rgba(200, 0, 0, 0.7);
  }
  :global([data-theme='nightly']) .bar-btn:hover {
    background: rgba(180, 0, 0, 0.15);
  }
  :global([data-theme='nightly']) .cancel-btn {
    color: #cc0000;
  }
  :global([data-theme='nightly']) .hint {
    color: rgba(200, 0, 0, 0.5);
  }
  :global([data-theme='nightly']) .result-row {
    border-bottom-color: rgba(180, 0, 0, 0.15);
  }
  :global([data-theme='nightly']) .result-row:active {
    background: rgba(180, 0, 0, 0.1);
  }
  :global([data-theme='nightly']) .act-btn {
    color: rgba(200, 0, 0, 0.6);
  }
  :global([data-theme='nightly']) .act-btn:hover {
    color: #cc0000;
    background: rgba(180, 0, 0, 0.15);
  }
  :global([data-theme='nightly']) .hl {
    color: #ee0000;
  }
</style>
