<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import CustomInput from './CustomInput.svelte'
  import OnScreenKeyboard from './OnScreenKeyboard.svelte'
  import { selectedObject } from '../stores/selectedObject.js'
  import { searchViewActive, pendingFocus } from '../stores/ui.js'
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

  function normQuery(s) {
    return s.trim().toLowerCase().replace(/\s+/g, '')
  }

  // Build searchable catalogue tokens for an object.
  // Bare numeric tokens are included for Messier/NGC/IC/Caldwell so that
  // searching "31" finds M31, "224" finds NGC 224, etc.
  // HIP/HD are prefix-only to avoid noise from thousands of bare numbers.
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
    if (!index) return []
    const nq = normQuery(q)
    if (!nq) return []

    const out = []
    const seen = new Set()

    function add(obj, display) {
      if (seen.has(obj.id)) return
      seen.add(obj.id)
      out.push({ obj, display, con: obj.constellation || null })
    }

    // Pass 0: prefix match on proper name (highest rank)
    for (const obj of index) {
      if (!obj.name) continue
      if (obj.name.toLowerCase().startsWith(nq)) add(obj, obj.name)
    }

    // Pass 1: prefix match on any catalogue number token
    for (const obj of index) {
      if (seen.has(obj.id)) continue
      const cats = catEntries(obj)
      for (const cat of cats) {
        if (cat.tokens.some((t) => t.startsWith(nq))) {
          add(obj, cat.label)
          break
        }
      }
    }

    // Pass 2: substring match on proper name (lowest rank)
    for (const obj of index) {
      if (seen.has(obj.id) || !obj.name) continue
      if (obj.name.toLowerCase().includes(nq)) add(obj, obj.name)
    }

    return out.slice(0, 20)
  }

  $: results = doSearch(query)

  function accept(item) {
    selectedObject.set(item.obj)
    if (item.obj.pos) pendingFocus.set({ ra: item.obj.pos[0], dec: item.obj.pos[1] })
    close()
  }

  function details(item) {
    // Stub — Object Details screen not yet implemented
    console.log('[Search] details:', item.obj.id)
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
    <button class="bar-btn cancel-btn" on:click={close}>Cancel</button>
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
          <span class="result-label">
            {item.display}{item.con ? ` (${item.con})` : ''}
          </span>
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
    color: #ffb0b0;
    --fg: #ffb0b0;
    --bg: #110000;
    --key-bg: rgba(180, 0, 0, 0.15);
  }
  :global([data-theme='nightly']) .search-bar {
    border-bottom-color: rgba(180, 0, 0, 0.2);
  }
  :global([data-theme='nightly']) .bar-btn {
    color: rgba(255, 160, 160, 0.7);
  }
  :global([data-theme='nightly']) .cancel-btn {
    color: #ff9090;
  }
  :global([data-theme='nightly']) .result-row {
    border-bottom-color: rgba(180, 0, 0, 0.15);
  }
  :global([data-theme='nightly']) .act-btn {
    color: rgba(255, 160, 160, 0.6);
  }
  :global([data-theme='nightly']) .act-btn:hover {
    color: #ffb0b0;
  }
</style>
