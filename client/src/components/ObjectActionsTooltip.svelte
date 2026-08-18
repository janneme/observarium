<script>
  import { createEventDispatcher } from 'svelte'
  import SkyViewIcon from '../icons/SkyViewIcon.svelte'
  import FinderViewIcon from '../icons/FinderViewIcon.svelte'
  import InfoIcon from '../icons/InfoIcon.svelte'
  import CloseIcon from '../icons/CloseIcon.svelte'

  const dispatch = createEventDispatcher()

  // The element the popover is positioned relative to - owned by the caller
  // (each screen's own object-name trigger), not by this component. Existing
  // purely while the caller wants it open, same pattern as
  // CustomSelect.svelte's popover (fixed position, flips upward/downward to
  // stay on-screen), but without owning a trigger of its own since every
  // caller's trigger markup differs (plain name, symbol+name button, etc.).
  export let anchor

  let popoverEl
  let style = ''

  $: if (anchor) updatePosition()

  function updatePosition() {
    const rect = anchor.getBoundingClientRect()
    const upward = rect.bottom > window.innerHeight / 2
    style = upward
      ? `left:${rect.left}px; bottom:${window.innerHeight - rect.top + 4}px; top:auto;`
      : `left:${rect.left}px; top:${rect.bottom + 4}px; bottom:auto;`
  }

  // Capture phase, matching CustomSelect.svelte - fires before any overlay's
  // own pointerdown|stopPropagation handler could swallow it, and (since this
  // component only exists while the caller renders it open) can never
  // spuriously fire on the same click that opened it. Also excludes the
  // anchor itself: a re-click on the trigger fires this pointerdown-capture
  // handler *before* the trigger's own click handler runs, so without this
  // exclusion re-clicking the same object would close it here and then the
  // trigger's own toggle-to-close logic (which runs later, on the
  // subsequent click event) would immediately reopen it, net result: no
  // visible close at all. Leaving anchor clicks alone here means that
  // toggle logic is the only thing that decides what a re-click does.
  function outside(e) {
    if (popoverEl && !popoverEl.contains(e.target) && !(anchor && anchor.contains(e.target))) dispatch('close')
  }

  function handleKey(e) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      dispatch('close')
    }
  }
</script>

<svelte:window on:pointerdown|capture={outside} on:keydown={handleKey} on:resize={updatePosition} />

<div class="tooltip" {style} bind:this={popoverEl} on:pointerdown|stopPropagation>
  <button
    class="act-btn"
    type="button"
    on:click={() => dispatch('skyview')}
    aria-label="Go to sky view"
    title="Sky view"
  >
    <SkyViewIcon size="1.4rem" aria-hidden="true" />
  </button>
  <button
    class="act-btn"
    type="button"
    on:click={() => dispatch('finder')}
    aria-label="Go to finder view"
    title="Finder view"
  >
    <FinderViewIcon size="1.4rem" aria-hidden="true" />
  </button>
  <button
    class="act-btn"
    type="button"
    on:click={() => dispatch('about')}
    aria-label="About object"
    title="About object"
  >
    <InfoIcon size="1.4rem" aria-hidden="true" />
  </button>
  <button class="act-btn close" type="button" on:click={() => dispatch('close')} aria-label="Close" title="Close">
    <CloseIcon size="1.4rem" aria-hidden="true" />
  </button>
</div>

<style>
  .tooltip {
    position: fixed;
    z-index: 500;
    display: flex;
    gap: 0.5rem;
    padding: 0.5rem;
    background: #0a0000;
    border: 1px solid rgba(200, 0, 0, 0.25);
    border-radius: 10px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
  }

  .act-btn {
    width: 2.75rem;
    height: 2.75rem;
    border: 1px solid rgba(232, 232, 232, 0.35);
    border-radius: 8px;
    background: none;
    cursor: pointer;
    color: var(--fg);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }

  .act-btn:hover {
    background: rgba(200, 0, 0, 0.12);
  }

  .act-btn.close {
    border-color: rgba(255, 120, 120, 0.5);
    color: #ff9a9a;
  }

  :global([data-theme='nightly']) .act-btn {
    border-color: rgba(200, 0, 0, 0.5);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .act-btn:hover {
    background: rgba(200, 0, 0, 0.18);
  }

  :global([data-theme='nightly']) .act-btn.close {
    border-color: rgba(200, 0, 0, 0.65);
    color: #ff0000;
  }
</style>
