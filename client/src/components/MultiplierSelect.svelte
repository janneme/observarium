<script>
  import { createEventDispatcher } from 'svelte'
  const dispatch = createEventDispatcher()

  export let value = 1
  export let options = [1]

  let open = false
  let optsStyle = ''
  let container

  function toggle() {
    if (!open) {
      const rect = container.getBoundingClientRect()
      const upward = rect.bottom > window.innerHeight / 2
      if (upward) {
        optsStyle = `left:${rect.left}px; bottom:${window.innerHeight - rect.top + 2}px; top:auto;`
      } else {
        optsStyle = `left:${rect.left}px; top:${rect.bottom + 2}px; bottom:auto;`
      }
    }
    open = !open
  }

  function pick(val) {
    open = false
    dispatch('change', val)
  }

  function outside(e) {
    if (open && container && !container.contains(e.target)) open = false
  }
</script>

<svelte:window on:pointerdown={outside} />

<div class="md" bind:this={container}>
  <button class="trigger" on:click|stopPropagation={toggle}>{value}x</button>
  {#if open}
    <div class="opts" style={optsStyle}>
      {#each options as opt}
        <button class="opt" class:cur={opt === value} on:click|stopPropagation={() => pick(opt)}>{opt}x</button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .md {
    position: relative;
    display: inline-block;
  }

  .trigger {
    border: 1px solid rgba(232, 232, 232, 0.26);
    background: #23232a;
    color: #e8e8e8;
    border-radius: 6px;
    padding: 0.2rem 0.45rem;
    font-size: 0.7rem;
    cursor: pointer;
    white-space: nowrap;
  }

  .opts {
    position: fixed;
    z-index: 500;
    background: #23232a;
    border: 1px solid rgba(232, 232, 232, 0.26);
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    min-width: 3.5rem;
    max-height: 180px;
    overflow-y: auto;
  }

  .opt {
    background: transparent;
    border: none;
    color: #e8e8e8;
    padding: 0.28rem 0.55rem;
    font-size: 0.7rem;
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
  }

  .opt:hover {
    background: rgba(255, 255, 255, 0.1);
  }

  .opt.cur {
    background: rgba(255, 255, 255, 0.15);
    font-weight: 600;
  }

  :global([data-theme='nightly']) .trigger {
    border-color: rgba(180, 0, 0, 0.4);
    background: #190000;
    color: #cc0000;
  }

  :global([data-theme='nightly']) .opts {
    background: #190000;
    border-color: rgba(180, 0, 0, 0.4);
  }

  :global([data-theme='nightly']) .opt {
    color: #cc0000;
  }

  :global([data-theme='nightly']) .opt:hover {
    background: rgba(180, 0, 0, 0.18);
  }

  :global([data-theme='nightly']) .opt.cur {
    background: rgba(180, 0, 0, 0.25);
  }
</style>
