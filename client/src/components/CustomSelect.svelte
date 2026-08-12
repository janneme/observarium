<script>
  import { createEventDispatcher } from 'svelte'
  const dispatch = createEventDispatcher()

  export let value = null
  export let options = [] // [{ value, label }]
  export let placeholder = 'Select…'
  export let disabled = false

  let open = false
  let optsStyle = ''
  let container

  $: current = options.find((o) => o.value === value) ?? null

  function toggle() {
    if (disabled) return
    if (!open) {
      const rect = container.getBoundingClientRect()
      const upward = rect.bottom > window.innerHeight / 2
      // min-width (not width) — the trigger itself can be much narrower than
      // its longest option (e.g. a cramped 2-column filter form), so the
      // open panel must be free to grow wider to avoid truncating option
      // text; it should never end up narrower than the trigger though.
      if (upward) {
        optsStyle = `left:${rect.left}px; min-width:${rect.width}px; bottom:${window.innerHeight - rect.top + 2}px; top:auto;`
      } else {
        optsStyle = `left:${rect.left}px; min-width:${rect.width}px; top:${rect.bottom + 2}px; bottom:auto;`
      }
    }
    open = !open
  }

  function pick(opt) {
    open = false
    dispatch('change', opt.value)
  }

  // Capture phase, not bubble - many full-screen overlays call
  // stopPropagation() on their own pointerdown handler (to keep clicks from
  // falling through to the sky view underneath), which would otherwise
  // prevent this bubble-phase window listener from ever seeing the event.
  // Capture fires on the way down, before any of that.
  function outside(e) {
    if (open && container && !container.contains(e.target)) open = false
  }

  function handleKey(e) {
    if (open && e.key === 'Escape') {
      open = false
      e.stopPropagation()
    }
  }
</script>

<svelte:window on:pointerdown|capture={outside} on:keydown={handleKey} />

<div class="cs" class:disabled bind:this={container}>
  <button class="trigger" type="button" {disabled} on:click|stopPropagation={toggle}>
    <span class="trigger-label" class:placeholder={!current}>{current ? current.label : placeholder}</span>
    <span class="chevron" class:open>▾</span>
  </button>
  {#if open}
    <div class="opts" style={optsStyle}>
      {#each options as opt (opt.value)}
        <button type="button" class="opt" class:cur={opt.value === value} on:click|stopPropagation={() => pick(opt)}
          >{opt.label}</button
        >
      {/each}
    </div>
  {/if}
</div>

<style>
  .cs {
    position: relative;
    flex: 1;
    min-width: 0;
  }

  .trigger {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    background: rgba(200, 0, 0, 0.07);
    border: 1px solid rgba(200, 0, 0, 0.25);
    color: var(--fg);
    border-radius: 6px;
    padding: 0.4rem 0.75rem;
    font-size: 1.02rem;
    cursor: pointer;
    text-align: left;
  }

  .trigger:hover {
    background: rgba(200, 0, 0, 0.12);
  }

  .cs.disabled .trigger {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .trigger-label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .trigger-label.placeholder {
    opacity: 0.6;
  }

  .chevron {
    flex-shrink: 0;
    font-size: 0.7rem;
    opacity: 0.6;
    transition: transform 120ms;
  }

  .chevron.open {
    transform: rotate(180deg);
  }

  .opts {
    position: fixed;
    z-index: 500;
    background: #0a0000;
    border: 1px solid rgba(200, 0, 0, 0.25);
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    width: max-content;
    max-width: min(90vw, 22rem);
    max-height: 260px;
    overflow-y: auto;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
  }

  .opt {
    background: transparent;
    border: none;
    color: var(--fg);
    padding: 0.5rem 0.75rem;
    font-size: 1.02rem;
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    /* Without this, a scrollable flex column container squeezes its children
       to fit rather than actually scrolling once there are enough options to
       exceed max-height (a long list, e.g. Object Type's ~14 entries, is
       exactly when this triggers) - rows get vertically compressed and their
       text overlaps the next row instead of the container scrolling. */
    flex-shrink: 0;
  }

  .opt:hover {
    background: rgba(200, 0, 0, 0.12);
  }

  .opt.cur {
    background: rgba(200, 0, 0, 0.2);
    font-weight: 600;
  }

  :global([data-theme='nightly']) .opts {
    background: #0a0000;
    border-color: rgba(180, 0, 0, 0.4);
  }

  :global([data-theme='nightly']) .opt:hover {
    background: rgba(180, 0, 0, 0.18);
  }

  :global([data-theme='nightly']) .opt.cur {
    background: rgba(180, 0, 0, 0.25);
  }
</style>
