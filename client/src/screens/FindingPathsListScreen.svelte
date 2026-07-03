<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import {
    getAllFindingPaths,
    deleteFindingPathForObject,
    incrementFindingPathsChanges,
    getSearchIndex,
  } from '../lib/db.js'
  import ObservationObjectSymbol from '../components/ObservationObjectSymbol.svelte'
  import ConfirmDialog from '../components/ConfirmDialog.svelte'
  import SearchPanel from '../components/SearchPanel.svelte'
  import CustomInput from '../components/CustomInput.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import PlusIcon from '../icons/PlusIcon.svelte'
  import DraftIcon from '../icons/DraftIcon.svelte'
  import EditIcon from '../icons/EditIcon.svelte'
  import DeleteIcon from '../icons/DeleteIcon.svelte'

  export let initialTargetChip = null
  export let initialStartChip = null

  const dispatch = createEventDispatcher()

  let allPaths = {}
  let objById = new Map()
  let starsByHip = new Map()
  let loading = true

  let targetChip = initialTargetChip
  let targetQuery = ''

  let startChip = initialStartChip
  let startQuery = ''

  let activeFilter = null // 'target' | 'start' | null
  let closeFilterTimer = null

  function onFilterFocusIn(which) {
    if (closeFilterTimer) {
      clearTimeout(closeFilterTimer)
      closeFilterTimer = null
    }
    activeFilter = which
  }

  function onFilterFocusOut() {
    closeFilterTimer = setTimeout(() => {
      activeFilter = null
      closeFilterTimer = null
    }, 150)
  }

  function selectFilterSuggestion(sug) {
    if (activeFilter === 'target') {
      targetChip = sug
      targetQuery = ''
    } else if (activeFilter === 'start') {
      startChip = sug
      startQuery = ''
    }
    activeFilter = null
  }

  let confirmOpen = false
  let pendingDeleteObjectId = null
  let pendingDeleteStartHip = null

  let addSearchOpen = false

  onMount(async () => {
    const [paths, index] = await Promise.all([getAllFindingPaths(), getSearchIndex()])
    const newObjById = new Map()
    const newStarsByHip = new Map()
    for (const obj of index) {
      newObjById.set(obj.id, obj)
      if (obj.hip != null) {
        const hipStr = String(obj.hip)
        if (!newStarsByHip.has(hipStr) || obj.type === 'star') {
          newStarsByHip.set(hipStr, obj)
        }
      }
    }
    objById = newObjById
    starsByHip = newStarsByHip
    allPaths = paths
    loading = false
  })

  function catalogLabel(obj) {
    if (!obj) return ''
    if (obj.m != null) return `M ${obj.m}`
    if (obj.ngc != null) return `NGC ${obj.ngc}`
    if (obj.ic != null) return `IC ${obj.ic}`
    if (obj.caldwell != null) return `C ${obj.caldwell}`
    return obj.name || String(obj.id || '')
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
    const first = (raw.split(/\s+/)[0] || '')
      .toLowerCase()
      .replace(/[0-9]+$/, '')
      .replace(/[._-]+$/, '')
    const greekChars = 'αβγδεζηθικλμνξοπρστυφχψω'
    if (first && greekChars.includes(first[0])) return first[0]
    const key = first.length >= 3 ? first.slice(0, 3) : first
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
    const greek = greekFromBayer(rawBay)
    if (greek && obj?.constellation) return `${greek} ${obj.constellation}`
    if (rawBay && obj?.constellation) return `${rawBay} ${obj.constellation}`
    if (obj?.hip != null) return `HIP ${obj.hip}`
    if (obj?.hd != null) return `HD ${obj.hd}`
    if (obj?.sao != null) return `SAO ${obj.sao}`
    if (obj?.flam != null && obj?.constellation) return `${obj.flam} ${obj.constellation}`
    return String(obj?.id || 'Star')
  }

  function getConst(label, obj) {
    if (!obj?.constellation) return null
    if (label.endsWith(' ' + obj.constellation)) return null
    return obj.constellation
  }

  function naturalSortKey(s) {
    const parts = []
    const re = /(\d+)|(\D+)/g
    let m
    while ((m = re.exec(String(s))) !== null) {
      if (m[1] != null) parts.push(parseInt(m[1], 10))
      else parts.push(m[2])
    }
    return parts
  }

  function naturalCompare(strA, strB) {
    const ka = naturalSortKey(strA)
    const kb = naturalSortKey(strB)
    const len = Math.min(ka.length, kb.length)
    for (let i = 0; i < len; i++) {
      const ai = ka[i],
        bi = kb[i]
      if (typeof ai === 'number' && typeof bi === 'number') {
        if (ai !== bi) return ai - bi
      } else if (typeof ai === 'string' && typeof bi === 'string') {
        if (ai !== bi) return ai < bi ? -1 : 1
      } else {
        return typeof ai === 'number' ? -1 : 1
      }
    }
    return ka.length - kb.length
  }

  function buildRows(paths, byId, byHip) {
    const result = []
    for (const [objectId, pathsByStart] of Object.entries(paths)) {
      const obj = byId.get(objectId)
      if (!obj) continue
      const targetLabel = catalogLabel(obj)
      if (!targetLabel) continue
      const targetConst = getConst(targetLabel, obj)
      const rowPaths = []
      for (const [startHip, path] of Object.entries(pathsByStart)) {
        const starObj = byHip.get(startHip)
        const starLabel = starObj ? preferredStarLabel(starObj) : `HIP ${startHip}`
        const starConst = starObj ? getConst(starLabel, starObj) : null
        const steps = path.steps || []
        const isDraft = steps.length === 0 || steps[steps.length - 1]?.final !== true
        const stepCount = steps.length
        rowPaths.push({ startHip, starLabel, starConst, isDraft, stepCount })
      }
      if (rowPaths.length === 0) continue
      result.push({ obj, targetLabel, targetConst, paths: rowPaths })
    }
    return result
  }

  function getDistinctStarts(rows) {
    const seen = new Set()
    const result = []
    for (const row of rows) {
      for (const p of row.paths) {
        const key = p.starLabel + (p.starConst ? ` (${p.starConst})` : '')
        if (!seen.has(key)) {
          seen.add(key)
          result.push({ label: key })
        }
      }
    }
    return result
  }

  function filterRows(rows, tChip, sChip) {
    let result = rows
    if (tChip) {
      result = result.filter((r) => {
        const rl = r.targetLabel + (r.targetConst ? ` (${r.targetConst})` : '')
        return rl === tChip.label
      })
    }
    if (sChip) {
      result = result
        .map((r) => ({
          ...r,
          paths: r.paths.filter((p) => {
            const pl = p.starLabel + (p.starConst ? ` (${p.starConst})` : '')
            return pl === sChip.label
          }),
        }))
        .filter((r) => r.paths.length > 0)
    }
    return result
  }

  $: allRows = buildRows(allPaths, objById, starsByHip)
  $: filteredRows = filterRows(allRows, targetChip, startChip)
  $: sortedRows = [...filteredRows].sort((a, b) => naturalCompare(a.targetLabel, b.targetLabel))
  $: targetSuggestions = allRows
    .filter((r) => {
      const lbl = r.targetLabel + (r.targetConst ? ` (${r.targetConst})` : '')
      return lbl.toLowerCase().includes(targetQuery.toLowerCase())
    })
    .map((r) => ({ label: r.targetLabel + (r.targetConst ? ` (${r.targetConst})` : '') }))
    .slice(0, 8)
  $: startSuggestions = getDistinctStarts(allRows)
    .filter((s) => s.label.toLowerCase().includes(startQuery.toLowerCase()))
    .slice(0, 8)

  async function doDelete() {
    confirmOpen = false
    const objId = pendingDeleteObjectId
    const hip = pendingDeleteStartHip
    pendingDeleteObjectId = null
    pendingDeleteStartHip = null
    await deleteFindingPathForObject(objId, hip)
    await incrementFindingPathsChanges()
    allPaths = await getAllFindingPaths()
  }
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={() => dispatch('close')}>←</button>
    <span class="header-title">Finding Paths</span>
    <button class="icon-btn add-btn" type="button" on:click={() => (addSearchOpen = true)} title="Add finding path">
      <PlusIcon size="1rem" />
    </button>
  </div>

  <div class="filter-bar">
    <div class="filter-group">
      <span class="filter-label">target:</span>
      {#if targetChip}
        <span class="chip"
          >{targetChip.label}<button
            class="chip-x"
            type="button"
            on:click={() => {
              targetChip = null
              targetQuery = ''
            }}>×</button
          ></span
        >
      {:else}
        <div class="input-wrap" on:focusin={() => onFilterFocusIn('target')} on:focusout={onFilterFocusOut}>
          <CustomInput
            bind:value={targetQuery}
            placeholder="filter…"
            outlined
            on:enter={() => {
              if (targetSuggestions.length > 0) selectFilterSuggestion(targetSuggestions[0])
            }}
          />
        </div>
      {/if}
    </div>

    <div class="filter-group">
      <span class="filter-label">start:</span>
      {#if startChip}
        <span class="chip"
          >{startChip.label}<button
            class="chip-x"
            type="button"
            on:click={() => {
              startChip = null
              startQuery = ''
            }}>×</button
          ></span
        >
      {:else}
        <div class="input-wrap" on:focusin={() => onFilterFocusIn('start')} on:focusout={onFilterFocusOut}>
          <CustomInput
            bind:value={startQuery}
            placeholder="filter…"
            outlined
            on:enter={() => {
              if (startSuggestions.length > 0) selectFilterSuggestion(startSuggestions[0])
            }}
          />
        </div>
      {/if}
    </div>
  </div>

  {#if activeFilter}
    <div class="filter-panel">
      <div class="filter-panel-kb">
        <OnScreenKeyboard />
      </div>
      <div class="filter-panel-results">
        {#each activeFilter === 'target' ? targetSuggestions : startSuggestions as sug}
          <button class="filter-result-row" type="button" on:click={() => selectFilterSuggestion(sug)}
            >{sug.label}</button
          >
        {/each}
        {#if (activeFilter === 'target' ? targetSuggestions : startSuggestions).length === 0}
          <div class="filter-no-results">No matches</div>
        {/if}
      </div>
    </div>
  {/if}

  <div class="content" class:hidden={activeFilter !== null}>
    {#if loading}
      <p class="empty-msg">Loading…</p>
    {:else if sortedRows.length === 0}
      <p class="empty-msg">No finding paths.</p>
    {:else}
      <table class="paths-table">
        <thead>
          <tr>
            <th class="col-target">Target</th>
            <th class="col-start">Start</th>
          </tr>
        </thead>
        <tbody>
          {#each sortedRows as row}
            <tr>
              <td class="target-cell">
                <button
                  class="target-btn"
                  type="button"
                  on:click={() => dispatch('openabout', { obj: row.obj, targetChip, startChip })}
                >
                  <ObservationObjectSymbol kind={objectSymbolKind(row.obj)} />
                  <strong>{row.targetLabel}</strong>{#if row.targetConst}&nbsp;({row.targetConst}){/if}
                </button>
              </td>
              <td class="paths-cell">
                {#each row.paths as p}
                  <div class="path-row">
                    <span class="path-info"
                      ><button
                        class="star-link"
                        type="button"
                        on:click={() =>
                          dispatch('openpath', {
                            contextObject: row.obj,
                            initialSelectStart: false,
                            initialStartHip: p.startHip,
                            targetChip,
                            startChip,
                          })}
                        ><strong>{p.starLabel}</strong>{#if p.starConst}&nbsp;({p.starConst}){/if}</button
                      >{#if p.isDraft}<sup class="draft-sup"><DraftIcon size="0.975rem" /></sup
                        >{/if}{#if !p.isDraft}<span class="step-count">&nbsp;–&nbsp;{p.stepCount}&nbsp;steps</span
                        >{/if}</span
                    >
                    <button
                      class="icon-btn edit-btn"
                      type="button"
                      title="Edit path"
                      on:click={() =>
                        dispatch('openpath', {
                          contextObject: row.obj,
                          initialSelectStart: false,
                          initialStartHip: null,
                          initialEditHip: p.startHip,
                          targetChip,
                          startChip,
                        })}
                    >
                      <EditIcon size="0.9rem" />
                    </button>
                    <button
                      class="icon-btn delete-btn"
                      type="button"
                      title="Delete path"
                      on:click={() => {
                        pendingDeleteObjectId = row.obj.id
                        pendingDeleteStartHip = p.startHip
                        confirmOpen = true
                      }}
                    >
                      <DeleteIcon size="0.9rem" />
                    </button>
                  </div>
                {/each}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</div>

<ConfirmDialog
  open={confirmOpen}
  title="Delete finding path"
  message="Delete this finding path?"
  confirmLabel="Delete"
  cancelLabel="Cancel"
  on:confirm={doDelete}
  on:cancel={() => {
    confirmOpen = false
    pendingDeleteObjectId = null
    pendingDeleteStartHip = null
  }}
/>

{#if addSearchOpen}
  <SearchPanel
    title="Select target object"
    placeholder="Search targets…"
    useSearchStore={false}
    manageSelection={false}
    includeSolar={false}
    showDetailsAction={false}
    showFindingPathsAction={false}
    autoCloseOnAccept={false}
    topOffset="2.75rem"
    zIndex={50}
    resultFilter={(obj) => obj.m != null || obj.ngc != null || obj.ic != null || obj.caldwell != null}
    onAcceptObject={(obj) => {
      addSearchOpen = false
      dispatch('openpath', {
        contextObject: obj,
        initialSelectStart: true,
        initialStartHip: null,
        targetChip,
        startChip,
      })
    }}
    on:close={() => {
      addSearchOpen = false
    }}
  />
{/if}

<style>
  .overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 40;
    background: #000;
    color: var(--fg);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .header {
    display: flex;
    align-items: center;
    height: 2.75rem;
    padding: 0 0.75rem;
    border-bottom: 1px solid rgba(232, 232, 232, 0.15);
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .back-btn {
    background: none;
    border: none;
    color: var(--fg);
    font-size: 0.9rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }

  .header-title {
    font-size: 1rem;
    font-weight: 600;
  }

  .add-btn {
    margin-left: auto;
  }

  .icon-btn {
    border: 1px solid rgba(232, 232, 232, 0.35);
    background: none;
    color: var(--fg);
    border-radius: 4px;
    width: 1.65rem;
    height: 1.65rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    line-height: 1;
  }

  .filter-bar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(232, 232, 232, 0.1);
    flex-shrink: 0;
  }

  .filter-group {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .filter-label {
    font-size: 0.82rem;
    color: rgba(232, 232, 232, 0.55);
    white-space: nowrap;
  }

  .input-wrap {
    position: relative;
  }

  :global(.filter-group .custom-input) {
    width: 8rem;
    min-height: unset;
    font-size: 0.82rem;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.2rem;
    background: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(232, 232, 232, 0.3);
    border-radius: 12px;
    padding: 0.15rem 0.25rem 0.15rem 0.5rem;
    font-size: 0.82rem;
    white-space: nowrap;
  }

  .chip-x {
    background: none;
    border: none;
    color: rgba(232, 232, 232, 0.7);
    cursor: pointer;
    font-size: 0.9rem;
    line-height: 1;
    padding: 0 0.1rem;
  }

  .filter-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .filter-panel-kb {
    flex-shrink: 0;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(232, 232, 232, 0.1);
  }

  .filter-panel-results {
    flex: 1;
    overflow-y: auto;
  }

  .filter-result-row {
    display: block;
    width: 100%;
    background: none;
    border: none;
    border-bottom: 1px solid rgba(232, 232, 232, 0.07);
    color: var(--fg);
    text-align: left;
    padding: 0.6rem 0.75rem;
    font-size: 0.9rem;
    cursor: pointer;
    font-family: inherit;
  }

  .filter-result-row:hover {
    background: rgba(255, 255, 255, 0.08);
  }

  .filter-no-results {
    padding: 1rem 0.75rem;
    color: rgba(232, 232, 232, 0.45);
    font-size: 0.9rem;
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem 0.75rem 1rem;
  }

  .content.hidden {
    display: none;
  }

  .empty-msg {
    color: rgba(232, 232, 232, 0.45);
    font-size: 0.9rem;
    padding: 1rem 0;
  }

  .paths-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }

  .paths-table th {
    text-align: left;
    font-size: 0.75rem;
    font-weight: 500;
    color: rgba(232, 232, 232, 0.55);
    padding: 0.3rem 0.5rem 0.3rem 0;
    border-bottom: 1px solid rgba(232, 232, 232, 0.1);
  }

  .col-target {
    width: 40%;
  }

  .col-start {
    width: 60%;
  }

  .paths-table tbody tr {
    border-bottom: 1px solid rgba(232, 232, 232, 0.07);
  }

  .target-cell {
    padding: 0.45rem 0.5rem 0.45rem 0;
    vertical-align: top;
  }

  .target-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: none;
    border: none;
    color: var(--fg);
    cursor: pointer;
    font-size: inherit;
    padding: 0;
    text-align: left;
  }

  .paths-cell {
    padding: 0.45rem 0 0.45rem 0;
    vertical-align: top;
  }

  .path-row {
    display: flex;
    align-items: baseline;
    gap: 0.35rem;
    padding: 0.1rem 0;
  }

  .path-info {
    flex: 1;
    display: inline;
  }

  .star-link {
    background: none;
    border: none;
    color: var(--fg);
    cursor: pointer;
    font-size: inherit;
    padding: 0;
    display: inline;
  }

  .draft-sup {
    display: inline-flex;
    align-items: center;
    vertical-align: super;
    line-height: 0;
    margin-left: 0.3rem;
    color: rgba(232, 232, 232, 0.6);
  }

  .step-count {
    font-size: 0.82rem;
    color: rgba(232, 232, 232, 0.6);
  }

  .delete-btn {
    flex-shrink: 0;
    align-self: center;
  }

  :global([data-theme='nightly']) .filter-label {
    color: rgba(200, 0, 0, 0.6);
  }

  :global([data-theme='nightly']) .chip {
    background: rgba(200, 0, 0, 0.1);
    border-color: rgba(200, 0, 0, 0.4);
  }

  :global([data-theme='nightly']) .chip-x {
    color: rgba(200, 0, 0, 0.7);
  }

  :global([data-theme='nightly'] .filter-group .custom-input.outlined) {
    border-color: rgba(200, 0, 0, 0.4);
    color: #cc0000;
  }

  :global([data-theme='nightly'] .filter-group .custom-input.outlined:focus) {
    border-color: rgba(200, 0, 0, 0.7);
    box-shadow: 0 0 0 2px rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .filter-bar {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .icon-btn {
    border-color: rgba(200, 0, 0, 0.55);
    color: #cc0000;
  }

  :global([data-theme='nightly']) .paths-table th {
    color: rgba(200, 0, 0, 0.6);
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .paths-table tbody tr {
    border-bottom-color: rgba(200, 0, 0, 0.15);
  }

  :global([data-theme='nightly']) .step-count {
    color: rgba(200, 0, 0, 0.6);
  }

  :global([data-theme='nightly']) .draft-sup {
    color: rgba(200, 0, 0, 0.6);
  }
</style>
