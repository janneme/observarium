<script>
  import { createEventDispatcher } from 'svelte'
  import TickIcon from '../icons/TickIcon.svelte'

  export let checked = false
  export let label = ''
  export let id = ''
  export let disabled = false

  const dispatch = createEventDispatcher()

  function toggle() {
    if (disabled) return
    checked = !checked
    dispatch('change', checked)
  }

  function onKeyDown(e) {
    if (disabled) return
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault()
      toggle()
    }
  }
</script>

<div class="checkbox-wrap" aria-disabled={disabled}>
  <button
    type="button"
    class="box"
    class:checked
    class:disabled
    role="checkbox"
    aria-checked={checked}
    aria-label={label || 'checkbox'}
    on:click={toggle}
    on:keydown={onKeyDown}
  >
    {#if checked}
      <TickIcon size="0.8rem" aria-hidden="true" />
    {/if}
  </button>
  {#if label}
    <label class="label" for={id || undefined}>{label}</label>
  {/if}
</div>

<style>
  .checkbox-wrap {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .box {
    width: 1.15rem;
    height: 1.15rem;
    border: 1px solid rgba(232, 232, 232, 0.55);
    border-radius: 4px;
    background: rgba(232, 232, 232, 0.02);
    color: #2e77ff;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    padding: 0;
  }

  .box.checked {
    border-color: rgba(46, 119, 255, 0.85);
    background: rgba(46, 119, 255, 0.14);
  }

  .box:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px rgba(46, 119, 255, 0.35);
  }

  .box.disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .label {
    font-size: 0.82rem;
    opacity: 0.9;
    cursor: default;
  }

  :global([data-theme='nightly']) .box {
    border-color: rgba(200, 0, 0, 0.6);
    background: rgba(200, 0, 0, 0.06);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .box.checked {
    border-color: #ff0000;
    background: rgba(200, 0, 0, 0.2);
  }

  :global([data-theme='nightly']) .box:focus-visible {
    box-shadow: 0 0 0 2px rgba(200, 0, 0, 0.35);
  }
</style>
