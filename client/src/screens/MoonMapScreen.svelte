<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import { MoonPhase, Observer, AstroTime, SearchRiseSet, SearchHourAngle, Body } from 'astronomy-engine'
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
  export let lat = 48.2
  export let lon = 16.37

  const dispatch = createEventDispatcher()
  // Persisted reactively (below) on every selection change, not just on an
  // explicit "back" action — closing the screen via Escape (MainScreen's
  // global shortcut handler) sets showMoonMap=false directly rather than
  // going through handleBack, so persistence must not depend on that path.
  const LAST_SELECTED_KEY = 'observarium.moonMap.lastSelected'

  let loading = true
  let allFeatures = []
  let featuresById = new Map()
  // Guards the persistence reactive statement below from firing (and
  // wiping the saved selection) before onMount has restored it.
  let didInitialLoad = false

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

  let moonPhasePercent = null
  let moonRiseTime = null
  let moonSetTime = null
  let moonMaxAltitude = null

  $: highlightId = selectedFeature?.id ?? null

  function updateViewing() {
    const vc = realViewingConditions(time)
    subLat = vc.subLat
    subLon = vc.subLon
    sunLon = phaseFull ? null : vc.sunLon
  }
  $: (time, phaseFull, updateViewing())

  // Illumination %, next rise/set, and next max altitude (transit) — relevant
  // only while nothing is selected (the header shows type/name/dimensions
  // for a selection instead). Searched forward from the current moment
  // (not from midnight) so an event that falls after midnight — e.g.
  // tonight's moonset at 0:13 — is still found instead of showing "-"
  // because it fell outside a midnight-to-midnight window.
  function updateMoonRiseSetPhase() {
    try {
      const phaseDeg = MoonPhase(time)
      moonPhasePercent = Math.round((1 - Math.cos((phaseDeg * Math.PI) / 180)) * 50)
      const observer = new Observer(lat, lon, 0)
      const startTime = new AstroTime(time)
      moonRiseTime = SearchRiseSet(Body.Moon, observer, +1, startTime, 1)
      moonSetTime = SearchRiseSet(Body.Moon, observer, -1, startTime, 1)
      const transit = SearchHourAngle(Body.Moon, observer, 0, startTime, +1)
      moonMaxAltitude = transit?.hor?.altitude ?? null
    } catch {
      moonPhasePercent = null
      moonRiseTime = null
      moonSetTime = null
      moonMaxAltitude = null
    }
  }
  $: (time, lat, lon, updateMoonRiseSetPhase())

  function persistSelection(feature) {
    if (typeof window === 'undefined') return
    try {
      if (feature) window.localStorage?.setItem(LAST_SELECTED_KEY, feature.id)
      else window.localStorage?.removeItem(LAST_SELECTED_KEY)
    } catch {
      return
    }
  }
  $: if (didInitialLoad) persistSelection(selectedFeature)

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
    didInitialLoad = true
  })
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <MoonMapHeader
    {selectedFeature}
    {phaseFull}
    {moonPhasePercent}
    {moonRiseTime}
    {moonSetTime}
    {moonMaxAltitude}
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
