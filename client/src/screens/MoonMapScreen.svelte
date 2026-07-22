<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import MoonMapHeader from '../components/MoonMapHeader.svelte'
  import MoonCanvas from '../components/MoonCanvas.svelte'
  import MoonDisambiguationOverlay from '../components/MoonDisambiguationOverlay.svelte'
  import SearchPanel from '../components/SearchPanel.svelte'
  import ObservationFormPanel from '../components/ObservationFormPanel.svelte'
  import { getMeta } from '../lib/db.js'
  import {
    flattenMoonFeatures,
    realViewingConditions,
    illumCos,
    buildMoonSearchIndex,
    doMoonSearch,
    MOON_MAP_MIN_VISIBLE_RATIO,
  } from '../lib/moonMap.js'

  export let time = new Date()

  const dispatch = createEventDispatcher()
  // Persisted only on leaving the screen (see handleBack) — deselecting
  // before leaving clears it, same as never having selected anything.
  const LAST_SELECTED_KEY = 'observarium.moonMap.lastSelected'

  let loading = true
  let allFeatures = []
  let featuresById = new Map()

  let selectedFeature = null
  // Terminator-cropped is the default (false) — see moon_map.md.
  let phaseFull = false
  let subLat = 0
  let subLon = 0
  let sunLon = null

  let showSearch = false
  let showObservationForm = false
  let disambigCandidates = null // null = overlay hidden
  let disambigLat = 0
  let disambigLon = 0
  let currentScale = 1

  let moonCanvasRef

  $: highlightId = selectedFeature?.id ?? null

  function updateViewing() {
    const vc = realViewingConditions(time)
    subLat = vc.subLat
    subLon = vc.subLon
    sunLon = phaseFull ? null : vc.sunLon
  }
  $: time, phaseFull, updateViewing()

  function persistSelection(feature) {
    if (typeof window === 'undefined') return
    try {
      if (feature) window.localStorage?.setItem(LAST_SELECTED_KEY, feature.id)
      else window.localStorage?.removeItem(LAST_SELECTED_KEY)
    } catch {
      return
    }
  }

  function selectFeature(feature) {
    selectedFeature = feature
    // If a terminator is shown and the feature isn't on the lit side,
    // switch to the full-disc view so it's actually visible.
    if (feature && sunLon != null && illumCos(feature.lat, feature.lon, sunLon) <= 0) {
      phaseFull = true
    }
  }

  function handleTap(e) {
    const { candidates, lat, lon } = e.detail
    if (candidates.length === 0) {
      selectedFeature = null
      return
    }
    if (candidates.length === 1) {
      selectFeature(candidates[0])
      return
    }
    disambigCandidates = candidates
    disambigLat = lat
    disambigLon = lon
  }

  function handleDisambigSelect(e) {
    disambigCandidates = null
    selectFeature(e.detail.feature)
  }

  function handleSearchAccept(e) {
    showSearch = false
    selectFeature(e.detail.object)
  }

  function handleBack() {
    persistSelection(selectedFeature)
    dispatch('close')
  }

  onMount(async () => {
    const raw = await getMeta('moon_features')
    allFeatures = flattenMoonFeatures(raw)
    featuresById = new Map(allFeatures.map((f) => [f.id, f]))
    updateViewing()
    if (typeof window !== 'undefined') {
      try {
        const savedId = window.localStorage?.getItem(LAST_SELECTED_KEY)
        // Silently falls back to the default view if the id no longer
        // resolves (e.g. the catalogue changed after a data update).
        if (savedId && featuresById.has(savedId)) selectFeature(featuresById.get(savedId))
      } catch {
        // ignore
      }
    }
    loading = false
  })
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <MoonMapHeader
    {selectedFeature}
    {phaseFull}
    on:back={handleBack}
    on:togglephase={() => (phaseFull = !phaseFull)}
    on:search={() => (showSearch = true)}
    on:observed={() => (showObservationForm = true)}
  />

  {#if loading}
    <p class="msg">Loading Moon feature data...</p>
  {:else}
    <div class="moon-wrap">
      <MoonCanvas
        bind:this={moonCanvasRef}
        bind:scale={currentScale}
        features={allFeatures}
        minVisibleRatio={MOON_MAP_MIN_VISIBLE_RATIO}
        interactive={true}
        {subLat}
        {subLon}
        {sunLon}
        {highlightId}
        on:tap={handleTap}
      />
    </div>
  {/if}

  {#if showSearch}
    <SearchPanel
      title="Search Moon Features"
      manageSelection={false}
      useSearchStore={false}
      includeSolar={false}
      showDetailsAction={false}
      showFindingPathsAction={false}
      indexLoader={async () => buildMoonSearchIndex(allFeatures)}
      searchFn={doMoonSearch}
      on:close={() => (showSearch = false)}
      on:accept={handleSearchAccept}
    />
  {/if}

  {#if disambigCandidates}
    <MoonDisambiguationOverlay
      candidates={disambigCandidates}
      {subLat}
      {subLon}
      {sunLon}
      lat={disambigLat}
      lon={disambigLon}
      scale={currentScale * 10}
      on:select={handleDisambigSelect}
    />
  {/if}

  {#if showObservationForm && selectedFeature}
    <ObservationFormPanel
      objectId={selectedFeature.id}
      {time}
      on:saved={() => (showObservationForm = false)}
      on:cancel={() => (showObservationForm = false)}
    />
  {/if}
</div>

<style>
  .overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 22;
    background: var(--bg);
    color: var(--fg);
    display: flex;
    flex-direction: column;
  }

  .msg {
    margin: 0.7rem;
    font-size: 0.86rem;
  }

  .moon-wrap {
    position: relative;
    flex: 1;
    min-height: 0;
  }
</style>
