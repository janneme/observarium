<script>
  import { createEventDispatcher } from 'svelte'
  import {
    showConstellationLines,
    showConstellationNames,
    showConstellationBoundaries,
    showDsos,
    showHorizon,
    showFovCircle,
    showSolarSystem,
    pendingChanges,
    skyPollution,
    nakedEyeLimitDisplay,
  } from '../stores/ui.js'
  import ConstellationLinesIcon from '../icons/ConstellationLinesIcon.svelte'
  import ConstellationNamesIcon from '../icons/ConstellationNamesIcon.svelte'
  import ConstellationBoundsIcon from '../icons/ConstellationBoundsIcon.svelte'
  import DsoIcon from '../icons/DsoIcon.svelte'
  import HorizonIcon from '../icons/HorizonIcon.svelte'
  import SolarSystemIcon from '../icons/SolarSystemIcon.svelte'
  import FovCircleIcon from '../icons/FovCircleIcon.svelte'
  import ObservationsIcon from '../icons/ObservationsIcon.svelte'
  import ObservedIcon from '../icons/ObservedIcon.svelte'
  import FindingPathsIcon from '../icons/FindingPathsIcon.svelte'
  import RangeIcon from '../icons/RangeIcon.svelte'
  import RiseSetIcon from '../icons/RiseSetIcon.svelte'
  import ListIcon from '../icons/ListIcon.svelte'
  import TelescopeIcon from '../icons/TelescopeIcon.svelte'
  import ConstellationQuizIcon from '../icons/ConstellationQuizIcon.svelte'
  import DsoQuizIcon from '../icons/DsoQuizIcon.svelte'
  import PlanetQuizIcon from '../icons/PlanetQuizIcon.svelte'
  import MoonQuizIcon from '../icons/MoonQuizIcon.svelte'
  import RefreshIcon from '../icons/RefreshIcon.svelte'
  import SyncIcon from '../icons/SyncIcon.svelte'
  import InfoIcon from '../icons/InfoIcon.svelte'
  import MoonMapIcon from '../icons/MoonMapIcon.svelte'

  export let open = false

  const dispatch = createEventDispatcher()

  function close() {
    dispatch('close')
  }
</script>

{#if open}
  <div class="menu-panel" on:pointerdown|stopPropagation>
    <div class="menu-sections">
      <!-- Section 1: Constellation toggles -->
      <div class="section-row">
        <button
          class="grid-item"
          class:off={!$showConstellationLines}
          on:click={() => showConstellationLines.update((v) => !v)}
          aria-label="Toggle constellation lines"
        >
          <div class="icon-wrap">
            <ConstellationLinesIcon size="42" />
          </div>
          <span class="item-lbl">Const.<br />Lines (c)</span>
        </button>

        <button
          class="grid-item"
          class:off={!$showConstellationNames}
          on:click={() => showConstellationNames.update((v) => !v)}
          aria-label="Toggle constellation names"
        >
          <div class="icon-wrap">
            <ConstellationNamesIcon size="42" />
          </div>
          <span class="item-lbl">Const.<br />Names (C)</span>
        </button>

        <button
          class="grid-item"
          class:off={!$showConstellationBoundaries}
          on:click={() => showConstellationBoundaries.update((v) => !v)}
          aria-label="Toggle constellation boundaries"
        >
          <div class="icon-wrap">
            <ConstellationBoundsIcon size="42" />
          </div>
          <span class="item-lbl">Const.<br />Bounds (b)</span>
        </button>
      </div>

      <!-- Section 2: Sky object toggles -->
      <div class="section-row">
        <button
          class="grid-item"
          class:off={!$showDsos}
          on:click={() => showDsos.update((v) => !v)}
          aria-label="Toggle deep sky objects"
        >
          <div class="icon-wrap">
            <DsoIcon size="42" />
          </div>
          <span class="item-lbl">DSO (d)</span>
        </button>

        <button
          class="grid-item"
          class:off={!$showSolarSystem}
          on:click={() => showSolarSystem.update((v) => !v)}
          aria-label="Toggle solar system"
        >
          <div class="icon-wrap">
            <SolarSystemIcon size="42" />
          </div>
          <span class="item-lbl">Solar<br />System (s)</span>
        </button>

        <button
          class="grid-item"
          class:off={!$showHorizon}
          on:click={() => showHorizon.update((v) => !v)}
          aria-label="Toggle horizon"
        >
          <div class="icon-wrap">
            <HorizonIcon size="42" />
          </div>
          <span class="item-lbl">Horizon (h)</span>
        </button>

        <button
          class="grid-item"
          class:off={!$showFovCircle}
          on:click={() => {
            showFovCircle.set(true)
            dispatch('fovcircle')
            close()
          }}
          aria-label="FOV circle"
        >
          <div class="icon-wrap">
            <FovCircleIcon size="42" />
          </div>
          <span class="item-lbl">FOV<br />Circle</span>
        </button>
      </div>

      <!-- Section 3: Records -->
      <div class="section-row">
        <button
          class="grid-item"
          on:click={() => {
            dispatch('observations')
            close()
          }}
          aria-label="Observations"
        >
          <div class="icon-wrap">
            <ObservationsIcon size="42" />
          </div>
          <span class="item-lbl">Observations (o)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('observedobjects')
            close()
          }}
          aria-label="Observed objects"
        >
          <div class="icon-wrap">
            <ObservedIcon size="42" />
          </div>
          <span class="item-lbl">Observed objects (O)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('lists')
            close()
          }}
          aria-label="Lists"
        >
          <div class="icon-wrap">
            <ListIcon size="42" />
          </div>
          <span class="item-lbl">Lists (l)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('findingpathslist')
            close()
          }}
          aria-label="Finding Paths"
        >
          <div class="icon-wrap">
            <FindingPathsIcon size="42px" />
          </div>
          <span class="item-lbl">Finding Paths (p)</span>
        </button>
      </div>

      <div class="section-row">
        <button
          class="grid-item"
          on:click={() => {
            dispatch('telescopes')
            close()
          }}
          aria-label="Telescopes"
        >
          <div class="icon-wrap">
            <TelescopeIcon size="42" />
          </div>
          <span class="item-lbl">Telescopes (t)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('visualrange')
            close()
          }}
          aria-label="Visual Range"
        >
          <div class="icon-wrap">
            <RangeIcon size="42" />
          </div>
          <span class="item-lbl">Visual Range (r)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('risesettimes')
            close()
          }}
          aria-label="Rise/Set Times"
        >
          <div class="icon-wrap">
            <RiseSetIcon size="42" />
          </div>
          <span class="item-lbl">Rise/Set Times (T)</span>
        </button>
      </div>

      <!-- Section 4: Quizzes -->
      <div class="section-row">
        <button
          class="grid-item"
          on:click={() => {
            dispatch('moonquiz')
            close()
          }}
          aria-label="Moon quiz"
        >
          <div class="icon-wrap">
            <MoonQuizIcon size="42" />
          </div>
          <span class="item-lbl">Moon Quiz (qm)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('starquiz')
            close()
          }}
          aria-label="Star quiz"
        >
          <div class="icon-wrap">
            <PlanetQuizIcon size="42" />
          </div>
          <span class="item-lbl">Star Quiz (qs)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('constellationquiz')
            close()
          }}
          aria-label="Constellation quiz"
        >
          <div class="icon-wrap">
            <ConstellationQuizIcon size="42" />
          </div>
          <span class="item-lbl">Const. Quiz (qc)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('deepskyquiz')
            close()
          }}
          aria-label="Deep sky quiz"
        >
          <div class="icon-wrap">
            <DsoQuizIcon size="42" />
          </div>
          <span class="item-lbl">DSO Quiz (qd)</span>
        </button>
      </div>

      <!-- Section 5: Data management -->
      <div class="section-row">
        <button
          class="grid-item"
          on:click={() => {
            dispatch('moonmap')
            close()
          }}
          aria-label="Moon map"
        >
          <div class="icon-wrap">
            <MoonMapIcon size="42" />
          </div>
          <span class="item-lbl">Moon Map (M)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('update')
            close()
          }}
          aria-label="Update object data"
        >
          <div class="icon-wrap">
            <RefreshIcon size="42" />
          </div>
          <span class="item-lbl">Update<br />Data (u)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('sync')
            close()
          }}
          aria-label="Synchronize observations"
        >
          <div class="icon-wrap">
            <SyncIcon size="42" />
            {#if $pendingChanges > 0}
              <span class="badge">{$pendingChanges}</span>
            {/if}
          </div>
          <span class="item-lbl">Sync (S)</span>
        </button>

        <button
          class="grid-item"
          on:click={() => {
            dispatch('about')
            close()
          }}
          aria-label="About"
        >
          <div class="icon-wrap">
            <InfoIcon size="42" />
          </div>
          <span class="item-lbl">About (a)</span>
        </button>
      </div>

      <!-- Section 6: Sky pollution -->
      <div class="section-row sky-pollution-row">
        <div class="sky-pollution">
          <div class="sky-pollution-header">
            <span class="sky-pollution-label">Sky pollution</span>
            <span class="sky-pollution-readout">Naked eye limit {nakedEyeLimitDisplay($skyPollution).toFixed(1)}</span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            step="0.5"
            value={$skyPollution}
            on:input={(e) => skyPollution.set(parseFloat(e.currentTarget.value))}
            aria-label="Sky pollution"
          />
          <div class="sky-pollution-endpoints">
            <span>Dark sky</span>
            <span>City</span>
          </div>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .menu-panel {
    position: fixed;
    top: 2.75rem;
    left: 0;
    height: calc(100vh - 2.75rem);
    width: 100vw;
    z-index: 20;
    background: var(--menu-bg);
    color: var(--surface-fg);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }

  .menu-sections {
    padding: 10px 8px 16px;
  }

  .section-row {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .grid-item {
    flex: 0 0 calc(25% - 4px);
    box-sizing: border-box;
    margin: 2px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding: 4px 2px;
    gap: 3px;
    background: #000;
    border: none;
    color: inherit;
    cursor: pointer;
    border-radius: 8px;
    transition: background 120ms;
    min-height: 76px;
  }

  .grid-item:hover {
    background: #1a1a1a;
  }
  .grid-item:active {
    background: #262626;
  }

  .icon-wrap {
    position: relative;
    flex-shrink: 0;
    display: flex;
    padding: 2px;
    --off-line-color: currentColor;
  }

  .icon-wrap :global(svg) {
    display: block;
  }

  .grid-item.off .icon-wrap::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(
      to top right,
      transparent calc(50% - 1px),
      var(--off-line-color) calc(50% - 1px),
      var(--off-line-color) calc(50% + 1px),
      transparent calc(50% + 1px)
    );
    pointer-events: none;
  }

  :global([data-theme='nightly']) .icon-wrap {
    --off-line-color: #0000ff;
  }

  .item-lbl {
    font-size: 0.78rem;
    line-height: 1.25;
    text-align: center;
    word-break: break-word;
    hyphens: auto;
    padding: 1px 3px;
  }

  :global([data-theme='nightly']) .grid-item {
    color: #ff0000;
  }

  /* Badge on sync icon */
  .badge {
    position: absolute;
    top: -4px;
    right: -6px;
    background: var(--accent);
    color: #fff;
    font-size: 0.6rem;
    font-weight: 700;
    min-width: 15px;
    height: 15px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 3px;
    line-height: 1;
  }

  :global([data-theme='nightly']) .badge {
    background: #1a3a6e;
    color: #ff4444;
  }

  .sky-pollution-row {
    margin: 2px;
  }

  .sky-pollution {
    width: 100%;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    gap: 4px;
    background: #000;
    border-radius: 8px;
    padding: 10px 12px;
  }

  .sky-pollution-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 0.85rem;
  }

  .sky-pollution-label {
    font-weight: 600;
  }

  .sky-pollution-readout {
    opacity: 0.7;
    font-size: 0.78rem;
  }

  .sky-pollution input[type='range'] {
    -webkit-appearance: none;
    appearance: none;
    width: 100%;
    height: 4px;
    margin: 6px 0;
    background: rgba(200, 0, 0, 0.25);
    border-radius: 2px;
    cursor: pointer;
  }

  .sky-pollution input[type='range']::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 1.1rem;
    height: 1.1rem;
    border-radius: 50%;
    background: var(--accent, #cc0000);
    cursor: pointer;
  }

  .sky-pollution input[type='range']::-moz-range-thumb {
    width: 1.1rem;
    height: 1.1rem;
    border: none;
    border-radius: 50%;
    background: var(--accent, #cc0000);
    cursor: pointer;
  }

  .sky-pollution input[type='range']::-moz-range-track {
    height: 4px;
    background: rgba(200, 0, 0, 0.25);
    border-radius: 2px;
  }

  .sky-pollution-endpoints {
    display: flex;
    justify-content: space-between;
    font-size: 0.72rem;
    opacity: 0.6;
  }

  :global([data-theme='nightly']) .sky-pollution-label,
  :global([data-theme='nightly']) .sky-pollution-readout,
  :global([data-theme='nightly']) .sky-pollution-endpoints {
    color: #ff0000;
  }
</style>
