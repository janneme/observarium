<script>
  import { createEventDispatcher } from 'svelte'
  import { typeLabel, formatDimensions } from '../lib/moonMap.js'
  import BackIcon from '../icons/BackIcon.svelte'
  import PhaseToggleIcon from '../icons/PhaseToggleIcon.svelte'
  import SearchIcon from '../icons/SearchIcon.svelte'
  import ObservedIcon from '../icons/ObservedIcon.svelte'

  export let selectedFeature = null
  export let phaseFull = false

  const dispatch = createEventDispatcher()

  // Omit the type label when the name already states it unambiguously
  // (e.g. "Mare Imbrium" already says "Mare") — see moon_map.md.
  function displayType(feature) {
    const label = typeLabel(feature.type)
    if (feature.name.toLowerCase().includes(label.toLowerCase())) return ''
    return label
  }
</script>

<div class="moon-map-header">
  <button class="icon-btn" on:click={() => dispatch('back')} aria-label="Back">
    <BackIcon size="1.2rem" />
  </button>
  <button class="icon-btn" on:click={() => dispatch('togglephase')} aria-label="Toggle phase view">
    <PhaseToggleIcon size="1.2rem" full={phaseFull} />
  </button>

  <span class="title">
    Moon{#if selectedFeature}
      {@const type = displayType(selectedFeature)}
      , {type ? `${type} ` : ''}{selectedFeature.name}{#if selectedFeature.sizeKm}, {formatDimensions(
          selectedFeature,
        )}{/if}
    {/if}
  </span>

  <div class="filler"></div>

  <button class="icon-btn" on:click={() => dispatch('search')} aria-label="Search Moon features">
    <SearchIcon size="1.2rem" />
  </button>
  {#if selectedFeature}
    <button class="icon-btn" on:click={() => dispatch('observed')} aria-label="Mark as observed">
      <ObservedIcon size="1.2rem" />
    </button>
  {/if}
</div>

<style>
  .moon-map-header {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.5rem 0.65rem;
    border-bottom: 1px solid rgba(180, 0, 0, 0.35);
    background: var(--bg);
    color: var(--fg);
  }

  .icon-btn {
    background: none;
    border: none;
    color: var(--fg);
    cursor: pointer;
    padding: 0.25rem 0.35rem;
    border-radius: 4px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .icon-btn:hover {
    background: rgba(200, 0, 0, 0.1);
  }

  .title {
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .filler {
    flex: 1;
  }
</style>
