<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import MoonCanvas from './MoonCanvas.svelte'

  // The small set of features that were already rendered near the tap
  // point in the main view — not re-queried/re-filtered at the tighter
  // zoom below (see moon_map.md "Selecting a feature").
  export let candidates = []
  export let subLat = 0
  export let subLon = 0
  export let sunLon = null
  export let lat = 0
  export let lon = 0
  export let scale = 10

  const dispatch = createEventDispatcher()
  let canvasRef

  function handleTap(e) {
    const { candidates: hit } = e.detail
    if (hit.length === 0) return
    // Smallest wins if the tap still resolves to more than one candidate
    // (e.g. deeply nested craters) — same size-ordering rule the map uses
    // for crater draw order/occlusion.
    const winner = hit.reduce((a, b) => (b.sizeDeg < a.sizeDeg ? b : a))
    dispatch('select', { feature: winner })
  }

  onMount(() => {
    canvasRef?.centerOn(lat, lon, scale)
  })
</script>

<div class="disambig-overlay" on:pointerdown|stopPropagation>
  <div class="square-container">
    <MoonCanvas
      bind:this={canvasRef}
      features={candidates}
      fixedFeatureSet={true}
      zoomEnabled={false}
      interactive={true}
      {subLat}
      {subLon}
      {sunLon}
      on:tap={handleTap}
    />
  </div>
  <p class="hint">Tap the feature you meant</p>
</div>

<style>
  .disambig-overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 100;
    background: #0a0a0a;
    display: flex;
    flex-direction: column;
    user-select: none;
  }

  .square-container {
    position: relative;
    flex-shrink: 0;
    width: calc(100vw - 2vh);
    aspect-ratio: 1;
    margin: 1vh 1vh 0;
    border-radius: 12px;
    overflow: hidden;
    touch-action: none;
  }

  .hint {
    margin: 1.2vh 1vh 0;
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.45);
    text-align: center;
  }

  :global([data-theme='nightly']) .disambig-overlay {
    background: #110000;
  }

  :global([data-theme='nightly']) .hint {
    color: rgba(200, 0, 0, 0.4);
  }
</style>
