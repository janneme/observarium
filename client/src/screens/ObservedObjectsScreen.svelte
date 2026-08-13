<script>
  import { onMount } from 'svelte'
  import {
    getAllObservedObjectIds,
    getObservationStatsByObject,
    getObjectsByIds,
    getMeta,
    getDoubleStarNear,
    getSearchIndex,
  } from '../lib/db.js'
  import { rawDifficulty, difficultyCategory } from '../lib/listDifficulty.js'
  import { naturalCompare } from '../lib/naturalSort.js'
  import {
    catalogLabel,
    fallbackLabelFromId,
    objectTypeKind,
    OBJECT_TYPE_LABELS,
    objectMatchesFilter,
    hasActiveFilter,
    describeFilter,
  } from '../lib/observedObjectsFilter.js'
  import { observedObjectsState } from '../stores/ui.js'
  import { keyboardActive } from '../stores/keyboard.js'
  import CustomSelect from '../components/CustomSelect.svelte'
  import CustomInput from '../components/CustomInput.svelte'
  import OnScreenKeyboard from '../components/OnScreenKeyboard.svelte'
  import ObservationObjectSymbol from '../components/ObservationObjectSymbol.svelte'
  import BackIcon from '../icons/BackIcon.svelte'

  export let onClose = () => {}
  export let onOpenObject = () => {}

  const SORT_OPTIONS = [
    { value: 'name', label: 'Name' },
    { value: 'newest', label: 'Newest first' },
    { value: 'oldest', label: 'Oldest first' },
    { value: 'easy', label: 'Easy first' },
    { value: 'hard', label: 'Hard first' },
    { value: 'count', label: 'Observation Number' },
  ]

  const OBS_COUNT_OPTIONS = [
    { value: null, label: 'Any' },
    { value: 1, label: '1' },
    { value: 2, label: '2' },
    { value: 3, label: '3' },
    { value: 4, label: '4' },
    { value: 5, label: '5' },
  ]

  let loading = true
  let telescopes = []
  let statsById = new Map()
  let objById = new Map()
  let computingDifficulty = false
  let catalogBounds = new Map()

  // Per-category {min, max} raw difficulty across the WHOLE catalogue (not
  // just observed objects) — the Difficulty column must read 10 for the
  // hardest object we know about, even if it's never been observed, not for
  // merely the hardest *observed* object (which made showpiece targets like
  // M81 read as "10/10" when the observed set skewed easy). Star-primaries
  // whose double-star pairs need an external position lookup are skipped
  // here (scoring the whole catalogue that way would mean one lookup per
  // such star) — the direct `double_star` catalogue records already give
  // full, representative coverage of that category's real range.
  function computeCatalogBounds(allObjects) {
    const bounds = new Map()
    for (const obj of allObjects) {
      if (obj.type === 'star' && obj.dbl && !Array.isArray(obj.dbl)) continue
      const category = difficultyCategory(obj)
      const raw = rawDifficulty(obj, null)
      if (!Number.isFinite(raw)) continue
      const b = bounds.get(category)
      if (!b) bounds.set(category, { min: raw, max: raw })
      else {
        if (raw < b.min) b.min = raw
        if (raw > b.max) b.max = raw
      }
    }
    return bounds
  }

  onMount(async () => {
    const [ids, stats, savedTelescopes, fullCatalog] = await Promise.all([
      getAllObservedObjectIds(),
      getObservationStatsByObject(),
      getMeta('telescopes'),
      getSearchIndex(),
    ])
    statsById = stats
    telescopes = Array.isArray(savedTelescopes) ? savedTelescopes : []
    catalogBounds = computeCatalogBounds(fullCatalog)
    const found = await getObjectsByIds([...ids])
    const nextObjById = new Map()
    for (const id of ids) nextObjById.set(id, found.get(id) || null)
    objById = nextObjById
    loading = false
  })

  // Icon symbol kind — separate from objectTypeKind (which groups broadly for
  // filtering purposes) since the symbol needs the precise per-body glyph for
  // solar-system objects.
  function symbolKind(obj) {
    if (!obj) return 'generic'
    if (obj.type === 'solar_system_body') return String(obj.name || '').toLowerCase() || 'generic'
    return objectTypeKind(obj)
  }

  function formatDate(dateKey) {
    if (!dateKey) return ''
    const d = new Date(`${dateKey}T00:00:00`)
    if (Number.isNaN(d.getTime())) return dateKey
    return `${d.getDate()}. ${d.getMonth() + 1}. ${d.getFullYear()}`
  }

  // "Telescopes" column — just the aperture, per observed_objects.md, for
  // every telescope actually seen through (stat.telescopeIds).
  function telescopeDiametersLabel(stat, telescopeList) {
    if (!stat?.telescopeIds?.size) return ''
    const diameters = [...stat.telescopeIds]
      .map((id) => telescopeList.find((t) => t.id === id)?.diameterInches)
      .filter((d) => d != null)
      .sort((a, b) => a - b)
    return diameters.map((d) => `${d}″`).join(', ')
  }

  // Maps a raw difficulty value onto the 1-10 scale using the whole
  // catalogue's per-category min/max (see computeCatalogBounds) — 1 is the
  // easiest object in the catalogue for that category, 10 the hardest.
  function rawToScale(raw, category, bounds) {
    const b = bounds.get(category)
    if (!b || !Number.isFinite(raw)) return null
    if (b.max === b.min) return 1
    const t = (raw - b.min) / (b.max - b.min)
    return Math.max(1, Math.min(10, Math.round(1 + t * 9)))
  }

  $: filter = $observedObjectsState.filter
  $: sort = $observedObjectsState.sort
  $: hideActive = $observedObjectsState.hideActive

  function updateFilter(patch) {
    observedObjectsState.update((s) => ({ ...s, filter: { ...s.filter, ...patch } }))
  }

  function setSort(value) {
    observedObjectsState.update((s) => ({ ...s, sort: value }))
  }

  function applySkyViewFilter() {
    observedObjectsState.update((s) => ({ ...s, hideActive: true }))
  }

  function cancelSkyViewFilter() {
    observedObjectsState.update((s) => ({ ...s, hideActive: false }))
  }

  $: allRows = [...objById.entries()].map(([id, obj]) => {
    const stat = statsById.get(id)
    return { id, obj, label: catalogLabel(obj) || fallbackLabelFromId(id), stat }
  })

  $: availableYears = [...new Set([...statsById.values()].flatMap((s) => [...s.countsByYear.keys()]))].sort(
    (a, b) => b - a,
  )
  $: yearOptions = [{ value: null, label: 'Any' }, ...availableYears.map((y) => ({ value: y, label: String(y) }))]
  $: telescopeOptions = [
    { value: null, label: 'Any telescope' },
    ...telescopes.map((t) => ({ value: t.id, label: t.name })),
  ]
  $: objectTypeOptions = [
    { value: null, label: 'Any' },
    ...Object.entries(OBJECT_TYPE_LABELS).map(([value, label]) => ({ value, label })),
  ]

  $: filteredRows = allRows.filter((row) => objectMatchesFilter(row.obj, row.id, filter, row.stat))

  // Per-row difficulty (1-10, global catalogue scale) — computed once per
  // filteredRows/catalogBounds change, independent of the current sort,
  // since the Difficulty column needs it regardless of what the list is
  // sorted by.
  let difficultyById = new Map()
  let difficultyNonce = 0
  async function recomputeDifficulty(rows, bounds) {
    const nonce = ++difficultyNonce
    computingDifficulty = true
    const scorable = rows.filter((r) => r.obj)
    const needsLookup = scorable.filter(
      (r) => r.obj.type === 'star' && r.obj.dbl && !Array.isArray(r.obj.dbl) && Array.isArray(r.obj.pos),
    )
    const entries = await Promise.all(
      needsLookup.map(async (r) => [r.id, await getDoubleStarNear(r.obj.pos[0], r.obj.pos[1])]),
    )
    if (nonce !== difficultyNonce) return
    const dsById = new Map(entries.filter(([, ds]) => ds))

    const nextDifficultyById = new Map()
    for (const r of scorable) {
      const category = difficultyCategory(r.obj)
      const raw = rawDifficulty(r.obj, dsById.get(r.id))
      const scale = rawToScale(raw, category, bounds)
      if (scale != null) nextDifficultyById.set(r.id, scale)
    }
    difficultyById = nextDifficultyById
    computingDifficulty = false
  }

  $: recomputeDifficulty(filteredRows, catalogBounds)

  $: sortedRows = (() => {
    const rows = filteredRows
    if (sort === 'newest') {
      return [...rows].sort((a, b) => (b.stat?.lastObserved || '').localeCompare(a.stat?.lastObserved || ''))
    }
    if (sort === 'oldest') {
      return [...rows].sort((a, b) => (a.stat?.lastObserved || '').localeCompare(b.stat?.lastObserved || ''))
    }
    if (sort === 'count') {
      return [...rows].sort((a, b) => (b.stat?.totalCount || 0) - (a.stat?.totalCount || 0))
    }
    if (sort === 'easy' || sort === 'hard') {
      const sign = sort === 'easy' ? 1 : -1
      return [...rows].sort((a, b) => {
        const da = difficultyById.get(a.id)
        const db = difficultyById.get(b.id)
        if (da == null && db == null) return 0
        if (da == null) return 1
        if (db == null) return -1
        return sign * (da - db)
      })
    }
    return [...rows].sort((a, b) => naturalCompare(a.label, b.label))
  })()

  $: headerCount = hasActiveFilter(filter) ? `${filteredRows.length}/${objById.size}` : `${objById.size}`
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={onClose} aria-label="Close">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="header-title">Observed objects ({headerCount})</span>
  </div>

  <div class="content">
    <div class="sort-row">
      <span class="field-label">Sort</span>
      <CustomSelect value={sort} options={SORT_OPTIONS} on:change={(e) => setSort(e.detail)} />
      {#if computingDifficulty}<span class="sorting-hint">computing difficulty…</span>{/if}
    </div>

    <div class="filter-form">
      <div class="field-row">
        <span class="field-label">Telescope</span>
        <CustomSelect
          value={filter.telescopeId}
          options={telescopeOptions}
          disabled={telescopes.length === 0}
          on:change={(e) => updateFilter({ telescopeId: e.detail })}
        />
      </div>
      <div class="field-row">
        <span class="field-label">Year</span>
        <CustomSelect
          value={filter.year}
          options={yearOptions}
          disabled={availableYears.length === 0}
          on:change={(e) => updateFilter({ year: e.detail })}
        />
      </div>
      <div class="field-row obs-row span-2">
        <span class="field-label">Observations</span>
        <span class="obs-sublabel">min</span>
        <CustomSelect
          value={filter.minObs}
          options={OBS_COUNT_OPTIONS}
          on:change={(e) => updateFilter({ minObs: e.detail })}
        />
        <span class="obs-sublabel">max</span>
        <CustomSelect
          value={filter.maxObs}
          options={OBS_COUNT_OPTIONS}
          on:change={(e) => updateFilter({ maxObs: e.detail })}
        />
      </div>
      <div class="field-row span-2 name-row">
        <span class="field-label">Name</span>
        <CustomInput
          value={filter.name}
          placeholder="e.g. NGC 2* or M.1"
          outlined
          on:input={(e) => updateFilter({ name: e.detail })}
        />
      </div>
      <div class="field-row">
        <span class="field-label">Object Type</span>
        <CustomSelect
          value={filter.objectType}
          options={objectTypeOptions}
          on:change={(e) => updateFilter({ objectType: e.detail })}
        />
      </div>
    </div>

    <div class="filter-actions">
      <button class="btn" type="button" on:click={applySkyViewFilter}> Filter Sky View </button>
      {#if hideActive}
        <button class="btn ghost" type="button" on:click={cancelSkyViewFilter}>Cancel Sky View Filter</button>
      {/if}
    </div>
    {#if hideActive}
      <div class="active-filter-desc">Active filter: {describeFilter(filter, telescopes)}</div>
    {/if}

    {#if loading}
      <p class="empty-msg">Loading…</p>
    {:else if sortedRows.length === 0}
      <p class="empty-msg">No observed objects match this filter.</p>
    {:else}
      <table class="rows-table">
        <thead>
          <tr>
            <th class="col-object">Object</th>
            <th class="col-difficulty">Difficulty</th>
            <th class="col-date">Last observed</th>
            <th class="col-count">Number<br />of obs.</th>
            <th class="col-telescopes">Telescopes</th>
          </tr>
        </thead>
        <tbody>
          {#each sortedRows as row (row.id)}
            <tr>
              <td class="object-cell">
                <button
                  class="object-btn"
                  type="button"
                  on:click={() => row.obj && onOpenObject(row.obj)}
                  disabled={!row.obj}
                >
                  <ObservationObjectSymbol kind={symbolKind(row.obj)} />
                  <span>{row.label}</span>
                </button>
              </td>
              <td class="difficulty-cell">{difficultyById.has(row.id) ? difficultyById.get(row.id) : '—'}</td>
              <td class="date-cell">{formatDate(row.stat?.lastObserved)}</td>
              <td class="count-cell">{row.stat?.totalCount ?? 0}</td>
              <td class="telescopes-cell">{telescopeDiametersLabel(row.stat, telescopes)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  {#if $keyboardActive}<OnScreenKeyboard />{/if}
</div>

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
  }

  .header-title {
    font-size: 1.2rem;
    font-weight: 600;
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 0.75rem 1rem 1rem;
  }

  .sort-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.85rem;
  }

  .sorting-hint {
    font-size: 0.82rem;
    opacity: 0.6;
    font-style: italic;
  }

  .filter-form {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem 1rem;
    padding: 0.75rem;
    border: 1px solid rgba(232, 232, 232, 0.12);
    border-radius: 8px;
    margin-bottom: 0.6rem;
  }

  .field-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-width: 0;
  }

  .field-label {
    font-size: 0.92rem;
    min-width: 7rem;
    flex-shrink: 0;
    opacity: 0.8;
  }

  .span-2 {
    grid-column: 1 / -1;
  }

  .obs-row :global(.cs) {
    flex: 0 1 8rem;
  }

  .obs-sublabel {
    font-size: 0.85rem;
    opacity: 0.6;
    flex-shrink: 0;
  }

  /* CustomInput's own min-height/padding/font-size run taller than
     CustomSelect's trigger by default — match it so the Name field lines up
     with the rest of the filter form. */
  .name-row :global(.custom-input) {
    flex: 1;
    min-height: unset;
    padding: 0.4rem 0.75rem;
    font-size: 1.02rem;
  }

  .filter-actions {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.4rem;
  }

  .btn {
    background: var(--accent, #cc0000);
    border: none;
    color: #000000;
    border-radius: 6px;
    padding: 0.5rem 1rem;
    font-size: 0.92rem;
    font-weight: 600;
    cursor: pointer;
  }

  .btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .btn.ghost {
    background: none;
    color: var(--fg);
    border: 1px solid rgba(232, 232, 232, 0.3);
  }

  .active-filter-desc {
    font-size: 0.85rem;
    opacity: 0.75;
    margin-bottom: 0.85rem;
  }

  .empty-msg {
    color: rgba(232, 232, 232, 0.45);
    font-size: 0.9rem;
    padding: 1rem 0;
  }

  .rows-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }

  .rows-table th {
    text-align: left;
    font-size: 0.75rem;
    font-weight: 500;
    color: rgba(232, 232, 232, 0.55);
    padding: 0.3rem 0.5rem 0.3rem 0;
    border-bottom: 1px solid rgba(232, 232, 232, 0.1);
  }

  .col-difficulty,
  .col-date,
  .col-count,
  .col-telescopes {
    white-space: nowrap;
  }

  .rows-table tbody tr {
    border-bottom: 1px solid rgba(232, 232, 232, 0.07);
  }

  .object-cell {
    padding: 0.4rem 0.5rem 0.4rem 0;
  }

  .object-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: none;
    border: none;
    color: var(--fg);
    cursor: pointer;
    font-size: inherit;
    padding: 0;
    text-align: left;
  }

  .object-btn:disabled {
    cursor: default;
    opacity: 0.6;
  }

  .difficulty-cell,
  .date-cell,
  .count-cell,
  .telescopes-cell {
    padding: 0.4rem 0.5rem;
    white-space: nowrap;
    opacity: 0.85;
  }

  :global([data-theme='nightly']) .header {
    border-bottom-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .field-label,
  :global([data-theme='nightly']) .sorting-hint,
  :global([data-theme='nightly']) .active-filter-desc,
  :global([data-theme='nightly']) .empty-msg,
  :global([data-theme='nightly']) .rows-table th,
  :global([data-theme='nightly']) .difficulty-cell,
  :global([data-theme='nightly']) .date-cell,
  :global([data-theme='nightly']) .count-cell,
  :global([data-theme='nightly']) .telescopes-cell {
    color: rgba(200, 0, 0, 0.75);
  }

  :global([data-theme='nightly']) .filter-form {
    border-color: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .rows-table tbody tr {
    border-bottom-color: rgba(200, 0, 0, 0.15);
  }

  :global([data-theme='nightly']) .btn.ghost {
    border-color: rgba(200, 0, 0, 0.4);
    color: #ff0000;
  }

  :global([data-theme='nightly'] .name-row .custom-input.outlined) {
    border-color: rgba(200, 0, 0, 0.4);
    color: #ff0000;
  }

  :global([data-theme='nightly'] .name-row .custom-input.outlined:focus-within) {
    border-color: rgba(200, 0, 0, 0.7);
    box-shadow: 0 0 0 2px rgba(200, 0, 0, 0.2);
  }
</style>
