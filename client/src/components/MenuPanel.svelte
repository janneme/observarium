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
    finderViewActive,
    pendingChanges,
  } from '../stores/ui.js'
  import { theme, toggleTheme } from '../stores/theme.js'
  import NightModeIcon from '../icons/NightModeIcon.svelte'
  import ConstellationLinesIcon from '../icons/ConstellationLinesIcon.svelte'
  import ConstellationNamesIcon from '../icons/ConstellationNamesIcon.svelte'
  import ConstellationBoundsIcon from '../icons/ConstellationBoundsIcon.svelte'
  import DsoIcon from '../icons/DsoIcon.svelte'
  import HorizonIcon from '../icons/HorizonIcon.svelte'
  import SolarSystemIcon from '../icons/SolarSystemIcon.svelte'
  import FinderViewIcon from '../icons/FinderViewIcon.svelte'
  import FovCircleIcon from '../icons/FovCircleIcon.svelte'
  import ObservationsIcon from '../icons/ObservationsIcon.svelte'
  import TelescopeIcon from '../icons/TelescopeIcon.svelte'
  import FinderQuizIcon from '../icons/FinderQuizIcon.svelte'
  import ConstellationQuizIcon from '../icons/ConstellationQuizIcon.svelte'
  import DsoQuizIcon from '../icons/DsoQuizIcon.svelte'
  import PlanetQuizIcon from '../icons/PlanetQuizIcon.svelte'
  import MoonQuizIcon from '../icons/MoonQuizIcon.svelte'
  import RefreshIcon from '../icons/RefreshIcon.svelte'
  import SyncIcon from '../icons/SyncIcon.svelte'
  import InfoIcon from '../icons/InfoIcon.svelte'
  import StrikeOverlayIcon from '../icons/StrikeOverlayIcon.svelte'

  export let open = false

  const dispatch = createEventDispatcher()

  function close() {
    dispatch('close')
  }
  function stub() {
    close()
  }
</script>

{#if open}
  <div class="menu-panel" on:pointerdown|stopPropagation>
    <div class="menu-grid">
      <!-- 1: Toggle color scheme -->
      <button class="grid-item" class:off={$theme !== 'nightly'} on:click={toggleTheme} aria-label="Toggle night mode">
        <div class="icon-wrap">
          <NightModeIcon size="28" />
          {#if $theme !== 'nightly'}
            <span class="strike"><StrikeOverlayIcon /></span>
          {/if}
        </div>
        <span class="item-lbl">Night</span>
      </button>

      <!-- 2: Toggle constellation lines -->
      <button
        class="grid-item"
        class:off={!$showConstellationLines}
        on:click={() => showConstellationLines.update((v) => !v)}
        aria-label="Toggle constellation lines"
      >
        <div class="icon-wrap">
          <ConstellationLinesIcon size="28" />
          {#if !$showConstellationLines}
            <span class="strike"><StrikeOverlayIcon /></span>
          {/if}
        </div>
        <span class="item-lbl">Const.<br />Lines (c)</span>
      </button>

      <!-- 3: Toggle constellation names -->
      <button
        class="grid-item"
        class:off={!$showConstellationNames}
        on:click={() => showConstellationNames.update((v) => !v)}
        aria-label="Toggle constellation names"
      >
        <div class="icon-wrap">
          <ConstellationNamesIcon size="28" />
          {#if !$showConstellationNames}
            <span class="strike"><StrikeOverlayIcon /></span>
          {/if}
        </div>
        <span class="item-lbl">Const.<br />Names (C)</span>
      </button>

      <!-- 4: Toggle constellation boundaries -->
      <button
        class="grid-item"
        class:off={!$showConstellationBoundaries}
        on:click={() => showConstellationBoundaries.update((v) => !v)}
        aria-label="Toggle constellation boundaries"
      >
        <div class="icon-wrap">
          <ConstellationBoundsIcon size="28" />
          {#if !$showConstellationBoundaries}
            <span class="strike"><StrikeOverlayIcon /></span>
          {/if}
        </div>
        <span class="item-lbl">Const.<br />Bounds (b)</span>
      </button>

      <!-- 4: Toggle DSO -->
      <button
        class="grid-item"
        class:off={!$showDsos}
        on:click={() => showDsos.update((v) => !v)}
        aria-label="Toggle deep sky objects"
      >
        <div class="icon-wrap">
          <DsoIcon size="28" />
          {#if !$showDsos}
            <span class="strike"><StrikeOverlayIcon /></span>
          {/if}
        </div>
        <span class="item-lbl">DSO (d)</span>
      </button>

      <!-- 5: Toggle horizon -->
      <button
        class="grid-item"
        class:off={!$showHorizon}
        on:click={() => showHorizon.update((v) => !v)}
        aria-label="Toggle horizon"
      >
        <div class="icon-wrap">
          <HorizonIcon size="28" />
          {#if !$showHorizon}
            <span class="strike"><StrikeOverlayIcon /></span>
          {/if}
        </div>
        <span class="item-lbl">Horizon (h)</span>
      </button>

      <!-- 6: Toggle solar system -->
      <button
        class="grid-item"
        class:off={!$showSolarSystem}
        on:click={() => showSolarSystem.update((v) => !v)}
        aria-label="Toggle solar system"
      >
        <div class="icon-wrap">
          <SolarSystemIcon size="28" />
          {#if !$showSolarSystem}
            <span class="strike"><StrikeOverlayIcon /></span>
          {/if}
        </div>
        <span class="item-lbl">Solar<br />System (s)</span>
      </button>

      <!-- 7: Toggle normal / finder view -->
      <button
        class="grid-item"
        class:off={!$finderViewActive}
        on:click={() => finderViewActive.update((v) => !v)}
        aria-label="Toggle finder view"
      >
        <div class="icon-wrap">
          <FinderViewIcon size="28" />
          {#if !$finderViewActive}
            <span class="strike"><StrikeOverlayIcon /></span>
          {/if}
        </div>
        <span class="item-lbl">Finder<br />View (F)</span>
      </button>

      <!-- 7: Toggle FOV circle -->
      <button
        class="grid-item"
        class:off={!$showFovCircle}
        on:click={() => showFovCircle.update((v) => !v)}
        aria-label="Toggle FOV circle"
      >
        <div class="icon-wrap">
          <FovCircleIcon size="28" />
          {#if !$showFovCircle}
            <span class="strike"><StrikeOverlayIcon /></span>
          {/if}
        </div>
        <span class="item-lbl">FOV<br />Circle</span>
      </button>

      <!-- 8: Observations -->
      <button
        class="grid-item"
        on:click={() => {
          dispatch('observations')
          close()
        }}
        aria-label="Observations"
      >
        <div class="icon-wrap">
          <ObservationsIcon size="28" />
        </div>
        <span class="item-lbl">Observations (o)</span>
      </button>

      <!-- 10: Telescopes -->
      <button
        class="grid-item"
        on:click={() => {
          dispatch('telescopes')
          close()
        }}
        aria-label="Telescopes"
      >
        <div class="icon-wrap">
          <TelescopeIcon size="28" />
        </div>
        <span class="item-lbl">Telescopes (t)</span>
      </button>

      <!-- 11: Finder scope quiz -->
      <button class="grid-item" on:click={stub} aria-label="Finder scope quiz">
        <div class="icon-wrap">
          <FinderQuizIcon size="28" />
        </div>
        <span class="item-lbl">Finder<br />Quiz</span>
      </button>

      <!-- 12: Constellation quiz -->
      <button class="grid-item" on:click={stub} aria-label="Constellation quiz">
        <div class="icon-wrap">
          <ConstellationQuizIcon size="28" />
        </div>
        <span class="item-lbl">Const.<br />Quiz</span>
      </button>

      <!-- 13: Deep sky quiz -->
      <button class="grid-item" on:click={stub} aria-label="Deep sky quiz">
        <div class="icon-wrap">
          <DsoQuizIcon size="28" />
        </div>
        <span class="item-lbl">DSO<br />Quiz</span>
      </button>

      <!-- 14: Find planet quiz -->
      <button class="grid-item" on:click={stub} aria-label="Find planet quiz">
        <div class="icon-wrap">
          <PlanetQuizIcon size="28" />
        </div>
        <span class="item-lbl">Planet<br />Quiz</span>
      </button>

      <!-- 15: Moon quiz -->
      <button class="grid-item" on:click={stub} aria-label="Moon quiz">
        <div class="icon-wrap">
          <MoonQuizIcon size="28" />
        </div>
        <span class="item-lbl">Moon<br />Quiz</span>
      </button>

      <!-- 16: Update object data -->
      <button
        class="grid-item"
        on:click={() => {
          dispatch('update')
          close()
        }}
        aria-label="Update object data"
      >
        <div class="icon-wrap">
          <RefreshIcon size="28" />
        </div>
        <span class="item-lbl">Update<br />Data (u)</span>
      </button>

      <!-- 17: Synchronize observation data -->
      <button
        class="grid-item"
        on:click={() => {
          dispatch('sync')
          close()
        }}
        aria-label="Synchronize observations"
      >
        <div class="icon-wrap">
          <SyncIcon size="28" />
          {#if $pendingChanges > 0}
            <span class="badge">{$pendingChanges}</span>
          {/if}
        </div>
        <span class="item-lbl">Sync (S)</span>
      </button>

      <!-- 18: About -->
      <button
        class="grid-item"
        on:click={() => {
          dispatch('about')
          close()
        }}
        aria-label="About"
      >
        <div class="icon-wrap">
          <InfoIcon size="28" />
        </div>
        <span class="item-lbl">About (a)</span>
      </button>
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

  .menu-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 2px;
    padding: 10px 8px 16px;
  }

  .grid-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding: 10px 4px 8px;
    gap: 5px;
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    border-radius: 8px;
    transition: background 120ms;
    min-height: 64px;
  }

  .grid-item:hover {
    background: rgba(255, 255, 255, 0.08);
  }
  .grid-item:active {
    background: rgba(255, 255, 255, 0.15);
  }

  .icon-wrap {
    position: relative;
    width: 28px;
    height: 28px;
    flex-shrink: 0;
    transition: opacity 150ms;
  }

  .strike {
    position: absolute;
    inset: 0;
    width: 28px;
    height: 28px;
    pointer-events: none;
  }

  .strike :global(svg) {
    display: block;
    width: 100%;
    height: 100%;
  }

  .grid-item.off .icon-wrap {
    opacity: 0.38;
  }

  .item-lbl {
    font-size: 0.65rem;
    line-height: 1.25;
    text-align: center;
    opacity: 0.75;
    word-break: break-word;
    hyphens: auto;
  }

  .grid-item.off .item-lbl {
    opacity: 0.45;
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
</style>
