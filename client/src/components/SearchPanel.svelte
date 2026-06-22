<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import CustomInput from './CustomInput.svelte'
  import OnScreenKeyboard from './OnScreenKeyboard.svelte'
  import { selectedObject } from '../stores/selectedObject.js'
  import { searchViewActive, objectDetailsActive, pendingFocus, solarSystemPositions } from '../stores/ui.js'
  import { doSearch } from '../lib/search.js'
  import { getSearchIndex } from '../lib/db.js'

  let query = ''
  let results = []
  let index = null
  let loading = true
  let inputComp

  function onKey(e) {
    if (e.key === 'Escape') close()
  }

  onMount(async () => {
    window.addEventListener('keydown', onKey)
    index = await getSearchIndex()
    loading = false
    await tick()
    inputComp?.focus()
  })

  onDestroy(() => {
    window.removeEventListener('keydown', onKey)
  })

  function close() {
    searchViewActive.set(false)
  }

  $: solarEntries = $solarSystemPositions.map((b) => ({
    id: `solar_${b.imageId || b.name.toLowerCase()}`,
    name: b.name,
    pos: [b.ra, b.dec],
    type: 'solar_system_body',
    bodyClass: b.bodyClass,
  }))

  $: results = doSearch(query, index ? [...solarEntries, ...index] : solarEntries.length ? solarEntries : null)

  function accept(item) {
    selectedObject.set(item.obj)
    if (item.obj.pos) pendingFocus.set({ ra: item.obj.pos[0], dec: item.obj.pos[1] })
    close()
  }

  function details(item) {
    selectedObject.set(item.obj)
    searchViewActive.set(false)
    objectDetailsActive.set(true)
  }

  function findingPaths(item) {
    // Stub — Finding Paths screen not yet implemented
    console.log('[Search] findingPaths:', item.obj.id)
  }
</script>

<div class="search-overlay" on:pointerdown|stopPropagation>
  <div class="search-bar">
    <div class="input-wrap">
      <CustomInput
        bind:this={inputComp}
        bind:value={query}
        placeholder="Search objects…"
        on:enter={() => results[0] && accept(results[0])}
        on:shiftEnter={() => results[0] && details(results[0])}
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
      <div class="hint">Type to search</div>
    {:else if results.length === 0}
      <div class="hint">No results</div>
    {:else}
      {#each results as item (item.obj.id)}
        <div class="result-row">
          <span class="result-label"
            >{#each item.spans as span}{#if span.hl}<span class="hl">{span.text}</span
                >{:else}{span.text}{/if}{/each}{#if item.showCon && item.obj.constellation}{' '}({item.obj
                .constellation}){/if}</span
          >
          <div class="result-actions">
            <button class="act-btn" on:click={() => accept(item)} title="Accept" aria-label="Accept">✓</button>
            <button class="act-btn" on:click={() => details(item)} title="Details" aria-label="Details">ℹ</button>
            <button class="act-btn" on:click={() => findingPaths(item)} title="Finding Paths" aria-label="Finding Paths"
              >◎</button
            >
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
    padding: 0.65rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
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
    font-size: 1.1rem;
    width: 2.2rem;
    height: 2.2rem;
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
