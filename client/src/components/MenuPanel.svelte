<script>
  import { createEventDispatcher } from 'svelte'
  import {
    showConstellationLines,
    showConstellationNames,
    showConstellationBoundaries,
    showDsos,
    showHorizon,
    showFovCircle,
    finderViewActive,
    pendingChanges,
  } from '../stores/ui.js'
  import { theme, toggleTheme } from '../stores/theme.js'

  export let open = false

  const dispatch = createEventDispatcher()

  function close() { dispatch('close') }
  function stub() { close() }
</script>

{#if open}
<div class="menu-panel" on:pointerdown|stopPropagation>
  <div class="menu-grid">

    <!-- 1: Toggle color scheme -->
    <button class="grid-item" class:off={$theme !== 'nightly'} on:click={toggleTheme} aria-label="Toggle night mode">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
        {#if $theme !== 'nightly'}
          <svg class="strike" viewBox="0 0 24 24"><line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
        {/if}
      </div>
      <span class="item-lbl">Night</span>
    </button>

    <!-- 2: Toggle constellation lines -->
    <button class="grid-item" class:off={!$showConstellationLines} on:click={() => showConstellationLines.update(v => !v)} aria-label="Toggle constellation lines">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
          <circle cx="4" cy="6" r="2" fill="currentColor" stroke="none"/>
          <circle cx="20" cy="8" r="1.6" fill="currentColor" stroke="none"/>
          <circle cx="14" cy="19" r="1.6" fill="currentColor" stroke="none"/>
          <line x1="4" y1="6" x2="20" y2="8" stroke-linecap="round"/>
          <line x1="20" y1="8" x2="14" y2="19" stroke-linecap="round"/>
          <line x1="4" y1="6" x2="14" y2="19" stroke-linecap="round"/>
        </svg>
        {#if !$showConstellationLines}
          <svg class="strike" viewBox="0 0 24 24"><line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
        {/if}
      </div>
      <span class="item-lbl">Const.<br>Lines</span>
    </button>

    <!-- 3: Toggle constellation names -->
    <button class="grid-item" class:off={!$showConstellationNames} on:click={() => showConstellationNames.update(v => !v)} aria-label="Toggle constellation names">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
          <circle cx="4" cy="6" r="2" fill="currentColor" stroke="none"/>
          <circle cx="20" cy="8" r="1.6" fill="currentColor" stroke="none"/>
          <circle cx="14" cy="19" r="1.6" fill="currentColor" stroke="none"/>
          <line x1="8" y1="9" x2="13" y2="11" stroke-linecap="round" stroke-width="1.2" stroke-dasharray="1.5 1.5"/>
          <text x="12" y="6" font-size="6" text-anchor="middle" fill="currentColor" stroke="none" style="font-style:italic">α</text>
        </svg>
        {#if !$showConstellationNames}
          <svg class="strike" viewBox="0 0 24 24"><line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
        {/if}
      </div>
      <span class="item-lbl">Const.<br>Names</span>
    </button>

    <!-- 4: Toggle constellation boundaries -->
    <button class="grid-item" class:off={!$showConstellationBoundaries} on:click={() => showConstellationBoundaries.update(v => !v)} aria-label="Toggle constellation boundaries">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-dasharray="3 2.2">
          <polygon points="12,3 21,8 21,16 12,21 3,16 3,8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        {#if !$showConstellationBoundaries}
          <svg class="strike" viewBox="0 0 24 24"><line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
        {/if}
      </div>
      <span class="item-lbl">Const.<br>Bounds</span>
    </button>

    <!-- 4: Toggle DSO -->
    <button class="grid-item" class:off={!$showDsos} on:click={() => showDsos.update(v => !v)} aria-label="Toggle deep sky objects">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
          <ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(-30 12 12)"/>
          <circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none"/>
        </svg>
        {#if !$showDsos}
          <svg class="strike" viewBox="0 0 24 24"><line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
        {/if}
      </div>
      <span class="item-lbl">DSO</span>
    </button>

    <!-- 5: Toggle horizon -->
    <button class="grid-item" class:off={!$showHorizon} on:click={() => showHorizon.update(v => !v)} aria-label="Toggle horizon">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M2 15 Q7 8 12 8 Q17 8 22 15"/>
          <line x1="2" y1="18" x2="22" y2="18"/>
        </svg>
        {#if !$showHorizon}
          <svg class="strike" viewBox="0 0 24 24"><line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
        {/if}
      </div>
      <span class="item-lbl">Horizon</span>
    </button>

    <!-- 6: Toggle normal / finder view -->
    <button class="grid-item" class:off={!$finderViewActive} on:click={() => finderViewActive.update(v => !v)} aria-label="Toggle finder view">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="8" cy="14" r="4.5"/>
          <circle cx="16" cy="14" r="4.5"/>
          <path d="M8 9.5 L8 7"/>
          <path d="M16 9.5 L16 7"/>
          <path d="M8 7 Q12 5 16 7"/>
          <line x1="11" y1="14" x2="13" y2="14" stroke-width="1.2"/>
        </svg>
        {#if !$finderViewActive}
          <svg class="strike" viewBox="0 0 24 24"><line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
        {/if}
      </div>
      <span class="item-lbl">Finder<br>View</span>
    </button>

    <!-- 7: Toggle FOV circle -->
    <button class="grid-item" class:off={!$showFovCircle} on:click={() => showFovCircle.update(v => !v)} aria-label="Toggle FOV circle">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2" stroke-linecap="round">
          <circle cx="12" cy="12" r="8"/>
          <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" style="stroke-dasharray:none"/>
        </svg>
        {#if !$showFovCircle}
          <svg class="strike" viewBox="0 0 24 24"><line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
        {/if}
      </div>
      <span class="item-lbl">FOV<br>Circle</span>
    </button>

    <!-- 8: Search -->
    <button class="grid-item" on:click={stub} aria-label="Search">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
          <circle cx="10.5" cy="10.5" r="6.5"/>
          <line x1="15.5" y1="15.5" x2="21" y2="21"/>
        </svg>
      </div>
      <span class="item-lbl">Search</span>
    </button>

    <!-- 9: Observations -->
    <button class="grid-item" on:click={stub} aria-label="Observations">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <rect x="4" y="2" width="14" height="20" rx="2"/>
          <line x1="8" y1="8" x2="16" y2="8"/>
          <line x1="8" y1="12" x2="16" y2="12"/>
          <line x1="8" y1="16" x2="13" y2="16"/>
        </svg>
      </div>
      <span class="item-lbl">Observations</span>
    </button>

    <!-- 10: Telescopes -->
    <button class="grid-item" on:click={stub} aria-label="Telescopes">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <rect x="2" y="9" width="15" height="6" rx="2"/>
          <line x1="17" y1="10" x2="22" y2="7"/>
          <line x1="17" y1="14" x2="22" y2="17"/>
          <line x1="9" y1="15" x2="7" y2="22"/>
          <line x1="9" y1="15" x2="11" y2="22"/>
        </svg>
      </div>
      <span class="item-lbl">Telescopes</span>
    </button>

    <!-- 11: Finder scope quiz -->
    <button class="grid-item" on:click={stub} aria-label="Finder scope quiz">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
          <circle cx="10" cy="12" r="7"/>
          <line x1="10" y1="5" x2="10" y2="8"/>
          <line x1="10" y1="16" x2="10" y2="19"/>
          <line x1="3" y1="12" x2="6" y2="12"/>
          <line x1="14" y1="12" x2="17" y2="12"/>
          <path d="M19 4 Q21 4 21 6 Q21 7.5 19.5 7.5 L19.5 9" stroke-width="1.3"/>
          <circle cx="19.5" cy="10.5" r="0.8" fill="currentColor" stroke="none"/>
        </svg>
      </div>
      <span class="item-lbl">Finder<br>Quiz</span>
    </button>

    <!-- 12: Constellation quiz -->
    <button class="grid-item" on:click={stub} aria-label="Constellation quiz">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
          <circle cx="4" cy="8" r="1.8" fill="currentColor" stroke="none"/>
          <circle cx="13" cy="4" r="1.5" fill="currentColor" stroke="none"/>
          <circle cx="19" cy="10" r="1.5" fill="currentColor" stroke="none"/>
          <circle cx="14" cy="17" r="1.5" fill="currentColor" stroke="none"/>
          <line x1="4" y1="8" x2="13" y2="4"/>
          <line x1="13" y1="4" x2="19" y2="10"/>
          <line x1="19" y1="10" x2="14" y2="17"/>
          <path d="M4 19 Q5.5 17.5 7 18.5 Q8 19.5 7 20.5 L6.5 21.5" stroke-width="1.3"/>
          <circle cx="6.5" cy="22.5" r="0.75" fill="currentColor" stroke="none"/>
        </svg>
      </div>
      <span class="item-lbl">Const.<br>Quiz</span>
    </button>

    <!-- 13: Deep sky quiz -->
    <button class="grid-item" on:click={stub} aria-label="Deep sky quiz">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
          <ellipse cx="11" cy="13" rx="8" ry="3.5" transform="rotate(-20 11 13)"/>
          <circle cx="11" cy="13" r="2" fill="currentColor" stroke="none"/>
          <path d="M19 3 Q21 3 21 5 Q21 6.5 19.5 6.5 L19.5 8" stroke-width="1.3"/>
          <circle cx="19.5" cy="9.5" r="0.75" fill="currentColor" stroke="none"/>
        </svg>
      </div>
      <span class="item-lbl">DSO<br>Quiz</span>
    </button>

    <!-- 14: Find planet quiz -->
    <button class="grid-item" on:click={stub} aria-label="Find planet quiz">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
          <circle cx="10" cy="14" r="5"/>
          <ellipse cx="10" cy="14" rx="9.5" ry="3" transform="rotate(-15 10 14)"/>
          <path d="M19 3 Q21 3 21 5 Q21 6.5 19.5 6.5 L19.5 8" stroke-width="1.3"/>
          <circle cx="19.5" cy="9.5" r="0.75" fill="currentColor" stroke="none"/>
        </svg>
      </div>
      <span class="item-lbl">Planet<br>Quiz</span>
    </button>

    <!-- 15: Moon quiz -->
    <button class="grid-item" on:click={stub} aria-label="Moon quiz">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M18 13.5A7 7 0 1 1 10.5 6a5 5 0 0 0 7.5 7.5z"/>
          <path d="M19 3 Q21 3 21 5 Q21 6.5 19.5 6.5 L19.5 8" stroke-width="1.3"/>
          <circle cx="19.5" cy="9.5" r="0.75" fill="currentColor" stroke="none"/>
        </svg>
      </div>
      <span class="item-lbl">Moon<br>Quiz</span>
    </button>

    <!-- 16: Update object data -->
    <button class="grid-item" on:click={stub} aria-label="Update object data">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="1,4 1,10 7,10"/>
          <path d="M3.51 15a9 9 0 1 0 .49-4.07"/>
        </svg>
      </div>
      <span class="item-lbl">Update<br>Data</span>
    </button>

    <!-- 17: Synchronize observation data -->
    <button class="grid-item" on:click={stub} aria-label="Synchronize observations">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23,4 23,10 17,10"/>
          <polyline points="1,20 1,14 7,14"/>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
        </svg>
        {#if $pendingChanges > 0}
          <span class="badge">{$pendingChanges}</span>
        {/if}
      </div>
      <span class="item-lbl">Sync</span>
    </button>

    <!-- 18: About -->
    <button class="grid-item" on:click={() => { dispatch('about'); close() }} aria-label="About">
      <div class="icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="16" x2="12" y2="12"/>
          <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
      </div>
      <span class="item-lbl">About</span>
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

.grid-item:hover { background: rgba(255,255,255,0.08); }
.grid-item:active { background: rgba(255,255,255,0.15); }

.icon-wrap {
  position: relative;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  transition: opacity 150ms;
}

.icon-wrap > svg:first-child {
  width: 28px;
  height: 28px;
}

.strike {
  position: absolute;
  inset: 0;
  width: 28px;
  height: 28px;
  pointer-events: none;
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
