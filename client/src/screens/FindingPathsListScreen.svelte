<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import {
    getAllFindingPaths,
    deleteFindingPathForObject,
    markDirty,
    getSyncDirtyTotalCount,
    getSearchIndex,
  } from '../lib/db.js'
  import { pendingChanges } from '../stores/ui.js'
  import { naturalCompare } from '../lib/naturalSort.js'
  import { recordPerfEvent } from '../lib/perf.js'
  import ObservationObjectSymbol from '../components/ObservationObjectSymbol.svelte'
  import ObjectActionsTooltip from '../components/ObjectActionsTooltip.svelte'
  import ConfirmDialog from '../components/ConfirmDialog.svelte'
  import SearchPanel from '../components/SearchPanel.svelte'
  import CustomInput from '../components/CustomInput.svelte'
  import CustomSelect from '../components/CustomSelect.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import PlusIcon from '../icons/PlusIcon.svelte'
  import DraftIcon from '../icons/DraftIcon.svelte'
  import EditIcon from '../icons/EditIcon.svelte'
  import DeleteIcon from '../icons/DeleteIcon.svelte'
  import BackIcon from '../icons/BackIcon.svelte'

  export let initialTargetChip = null
  export let initialStartChip = null

  const dispatch = createEventDispatcher()

  // Object-actions tooltip - only ever targets the TARGET object of a path
  // (whichever table column currently shows it - it swaps between column 1
  // and column 2 depending on sortMode, see the template). The "Start" star
  // keeps its old click-to-open-path role everywhere.
  let tooltipObj = null
  let tooltipAnchor = null

  function openTooltip(obj, e) {
    if (!obj || obj.type === 'moon_feature') return
    if (tooltipObj?.id === obj.id) {
      closeTooltip()
      return
    }
    tooltipObj = obj
    tooltipAnchor = e.currentTarget
  }

  function closeTooltip() {
    tooltipObj = null
    tooltipAnchor = null
  }

  let allPaths = {}
  let objById = new Map()
  let starsByHip = new Map()
  let loading = true

  let targetChip = initialTargetChip
  let targetQuery = ''

  let startChip = initialStartChip
  let startQuery = ''

  let showCompleted = true

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
    const t0 = performance.now()
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
    recordPerfEvent('finding_paths_list_load', performance.now() - t0, { catalogueSize: index.length })
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
    if (obj?.wds) return `WDS ${obj.wds}`
    return String(obj?.id || 'Star')
  }

  function getConst(label, obj) {
    if (!obj?.constellation) return null
    if (label.endsWith(' ' + obj.constellation)) return null
    return obj.constellation
  }

  const SORT_OPTIONS = [
    { value: 'target', label: 'Target' },
    { value: 'start', label: 'Start' },
    { value: 'newest', label: 'Newest first' },
  ]
  let sortMode = 'target'

  // One entry per individual (target, start) finding path - the shared basis
  // for both filtering/suggestions and the three sort modes below, since
  // which entity gets aggregated (target, start, or neither) differs per mode.
  function buildFlatPaths(paths, byId, byHip) {
    const result = []
    for (const [objectId, pathsByStart] of Object.entries(paths)) {
      const obj = byId.get(objectId)
      if (!obj) continue
      const targetLabel = catalogLabel(obj)
      if (!targetLabel) continue
      const targetConst = getConst(targetLabel, obj)
      for (const [startHip, path] of Object.entries(pathsByStart)) {
        const starObj = byHip.get(startHip)
        const starLabel = starObj ? preferredStarLabel(starObj) : `HIP ${startHip}`
        const starConst = starObj ? getConst(starLabel, starObj) : null
        const steps = path.steps || []
        const isDraft = steps.length === 0 || steps[steps.length - 1]?.final !== true
        const stepCount = steps.length
        result.push({
          objectId,
          startHip,
          obj,
          targetLabel,
          targetConst,
          starObj,
          starLabel,
          starConst,
          isDraft,
          stepCount,
          createdAt: path.createdAt || null,
        })
      }
    }
    return result
  }

  function distinctLabels(flat, labelOf, query) {
    const seen = new Set()
    const result = []
    for (const p of flat) {
      const label = labelOf(p)
      if (seen.has(label)) continue
      if (query && !label.toLowerCase().includes(query.toLowerCase())) continue
      seen.add(label)
      result.push({ label })
      if (result.length >= 8) break
    }
    return result
  }

  function filterFlatPaths(flat, tChip, sChip, showCompletedPaths) {
    let result = flat
    if (tChip) {
      result = result.filter((p) => p.targetLabel + (p.targetConst ? ` (${p.targetConst})` : '') === tChip.label)
    }
    if (sChip) {
      result = result.filter((p) => p.starLabel + (p.starConst ? ` (${p.starConst})` : '') === sChip.label)
    }
    if (!showCompletedPaths) {
      result = result.filter((p) => p.isDraft)
    }
    return result
  }

  // Groups filtered paths by target (primaryKind 'target') so every row is
  // one target object with its reachable starting stars listed underneath -
  // today's default view.
  function groupByTarget(flat) {
    const map = new Map()
    for (const p of flat) {
      if (!map.has(p.objectId)) {
        map.set(p.objectId, {
          key: p.objectId,
          primaryKind: 'target',
          obj: p.obj,
          label: p.targetLabel,
          const: p.targetConst,
          items: [],
        })
      }
      map.get(p.objectId).items.push(p)
    }
    return [...map.values()].sort((a, b) => naturalCompare(a.label, b.label))
  }

  // Mirror of groupByTarget, aggregating by start star instead - each row is
  // one starting star with its reachable targets listed underneath.
  function groupByStart(flat) {
    const map = new Map()
    for (const p of flat) {
      if (!map.has(p.startHip)) {
        map.set(p.startHip, {
          key: p.startHip,
          primaryKind: 'start',
          obj: p.starObj,
          label: p.starLabel,
          const: p.starConst,
          items: [],
        })
      }
      map.get(p.startHip).items.push(p)
    }
    return [...map.values()].sort((a, b) => naturalCompare(a.label, b.label))
  }

  // No aggregation - every individual path becomes its own single-item row,
  // newest createdAt first, so the same target/start pair can appear more
  // than once if it has been re-created.
  function ungroupedByNewest(flat) {
    return flat
      .slice()
      .sort((a, b) => (b.createdAt ? Date.parse(b.createdAt) : 0) - (a.createdAt ? Date.parse(a.createdAt) : 0))
      .map((p) => ({
        key: `${p.objectId}::${p.startHip}`,
        primaryKind: 'target',
        obj: p.obj,
        label: p.targetLabel,
        const: p.targetConst,
        items: [p],
      }))
  }

  $: allFlatPaths = buildFlatPaths(allPaths, objById, starsByHip)
  $: filteredFlatPaths = filterFlatPaths(allFlatPaths, targetChip, startChip, showCompleted)
  $: sortedRows =
    sortMode === 'start'
      ? groupByStart(filteredFlatPaths)
      : sortMode === 'newest'
        ? ungroupedByNewest(filteredFlatPaths)
        : groupByTarget(filteredFlatPaths)
  $: targetSuggestions = distinctLabels(
    allFlatPaths,
    (p) => p.targetLabel + (p.targetConst ? ` (${p.targetConst})` : ''),
    targetQuery,
  )
  $: startSuggestions = distinctLabels(
    allFlatPaths,
    (p) => p.starLabel + (p.starConst ? ` (${p.starConst})` : ''),
    startQuery,
  )

  async function doDelete() {
    confirmOpen = false
    const objId = pendingDeleteObjectId
    const hip = pendingDeleteStartHip
    pendingDeleteObjectId = null
    pendingDeleteStartHip = null
    await deleteFindingPathForObject(objId, hip)
    await markDirty('findingPaths', `${objId}::${hip}`, 'delete')
    pendingChanges.set(await getSyncDirtyTotalCount())
    allPaths = await getAllFindingPaths()
  }
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={() => dispatch('close')} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Finding Paths</span>
    <button class="icon-btn add-btn" type="button" on:click={() => (addSearchOpen = true)} title="Add finding path">
      <PlusIcon size="1rem" />
    </button>
  </div>

  <div class="filter-bar">
    <div class="filter-group">
      <span class="filter-label">from</span>
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
      <span class="filter-label">to</span>
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

    <label class="filter-group completed-toggle">
      <input type="checkbox" bind:checked={showCompleted} />
      <span class="filter-label">completed</span>
    </label>
  </div>

  <div class="sort-bar">
    <span class="filter-label">Sort:</span>
    <CustomSelect value={sortMode} options={SORT_OPTIONS} on:change={(e) => (sortMode = e.detail)} />
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
            <th class="col-target">{sortMode === 'start' ? 'Start' : 'Target'}</th>
            <th class="col-start">{sortMode === 'start' ? 'Targets' : 'Start'}</th>
          </tr>
        </thead>
        <tbody>
          {#each sortedRows as row (row.key)}
            <tr>
              <td class="target-cell">
                <button
                  class="target-btn"
                  type="button"
                  on:click={(e) =>
                    row.primaryKind === 'target'
                      ? openTooltip(row.obj, e)
                      : dispatch('openpath', {
                          contextObject: row.items[0]?.obj,
                          initialSelectStart: false,
                          initialStartHip: row.items[0]?.startHip ?? null,
                          targetChip,
                          startChip,
                        })}
                >
                  <ObservationObjectSymbol kind={objectSymbolKind(row.obj)} />
                  <strong>{row.label}</strong>{#if row.const}&nbsp;({row.const}){/if}
                </button>
              </td>
              <td class="paths-cell">
                {#each row.items as item}
                  <div class="path-row">
                    <span class="path-info"
                      ><button
                        class="star-link"
                        type="button"
                        on:click={(e) =>
                          row.primaryKind === 'start'
                            ? openTooltip(item.obj, e)
                            : dispatch('openpath', {
                                contextObject: item.obj,
                                initialSelectStart: false,
                                initialStartHip: item.startHip,
                                targetChip,
                                startChip,
                              })}
                        >{#if row.primaryKind === 'start'}<span class="item-symbol"
                            ><ObservationObjectSymbol kind={objectSymbolKind(item.obj)} /></span
                          >{/if}<strong>{row.primaryKind === 'start' ? item.targetLabel : item.starLabel}</strong
                        >{#if row.primaryKind === 'start' ? item.targetConst : item.starConst}&nbsp;({row.primaryKind ===
                          'start'
                            ? item.targetConst
                            : item.starConst}){/if}</button
                      >{#if item.isDraft}<sup class="draft-sup"><DraftIcon size="0.975rem" /></sup
                        >{/if}{#if !item.isDraft}<span class="step-count">&nbsp;–&nbsp;{item.stepCount}&nbsp;steps</span
                        >{/if}</span
                    >
                    <button
                      class="icon-btn edit-btn"
                      type="button"
                      title="Edit path"
                      on:click={() =>
                        dispatch('openpath', {
                          contextObject: item.obj,
                          initialSelectStart: false,
                          initialStartHip: null,
                          initialEditHip: item.startHip,
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
                        pendingDeleteObjectId = item.objectId
                        pendingDeleteStartHip = item.startHip
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

{#if tooltipObj}
  <ObjectActionsTooltip
    anchor={tooltipAnchor}
    on:skyview={() => {
      dispatch('gotoskyview', { object: tooltipObj })
      closeTooltip()
    }}
    on:finder={() => {
      dispatch('gotofinder', { object: tooltipObj })
      closeTooltip()
    }}
    on:about={() => {
      dispatch('openabout', { targetChip, startChip, obj: tooltipObj })
      closeTooltip()
    }}
    on:close={closeTooltip}
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
    gap: 0.35rem;
    flex-shrink: 0;
  }

  .back-btn {
    background: none;
    border: none;
    color: var(--fg);
    cursor: pointer;
    padding: 0.25rem 0.15rem 0.25rem 0.5rem;
    border-radius: 4px;
    display: flex;
    align-items: center;
    flex-shrink: 0;
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

  .sort-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(232, 232, 232, 0.1);
    flex-shrink: 0;
  }

  .item-symbol {
    display: inline-flex;
    align-items: center;
    vertical-align: middle;
    margin-right: 0.25rem;
  }

  .filter-label {
    font-size: 0.82rem;
    color: rgba(232, 232, 232, 0.55);
    white-space: nowrap;
  }

  .completed-toggle {
    margin-left: auto;
    cursor: pointer;
  }

  /* appearance: none + hand-drawn check, matching ListsScreen's "highlight
     observed" checkbox - the native unchecked box stays browser-default
     white regardless of theme, which clashes at night. */
  .completed-toggle input[type='checkbox'] {
    appearance: none;
    -webkit-appearance: none;
    width: 1rem;
    height: 1rem;
    margin: 0;
    flex-shrink: 0;
    border: 1.5px solid rgba(232, 232, 232, 0.4);
    border-radius: 3px;
    background: transparent;
    cursor: pointer;
    position: relative;
  }

  .completed-toggle input[type='checkbox']:checked {
    background: var(--accent, #cc0000);
    border-color: var(--accent, #cc0000);
  }

  .completed-toggle input[type='checkbox']:checked::after {
    content: '';
    position: absolute;
    left: 0.27rem;
    top: 0.06rem;
    width: 0.22rem;
    height: 0.48rem;
    border: solid #000000;
    border-width: 0 2px 2px 0;
    transform: rotate(45deg);
  }

  :global([data-theme='nightly']) .completed-toggle input[type='checkbox'] {
    border-color: rgba(200, 0, 0, 0.55);
  }

  .input-wrap {
    position: relative;
  }

  :global(.filter-group .custom-input) {
    width: 6.4rem;
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
    vertical-align: middle;
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
    align-items: center;
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
    color: #ff0000;
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

  :global([data-theme='nightly']) .sort-bar {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .icon-btn {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
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
