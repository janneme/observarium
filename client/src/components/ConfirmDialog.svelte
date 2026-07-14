<script>
  import { createEventDispatcher } from 'svelte'

  export let open = false
  export let title = 'Confirm'
  export let message = 'Are you sure?'
  export let confirmLabel = 'Confirm'
  export let cancelLabel = 'Cancel'

  const dispatch = createEventDispatcher()

  function close() {
    dispatch('cancel')
  }

  function confirmAction() {
    dispatch('confirm')
  }
</script>

{#if open}
  <div
    class="confirm-backdrop"
    role="button"
    tabindex="0"
    aria-label="Close confirmation dialog"
    on:pointerdown|stopPropagation
    on:click={close}
    on:keydown={(e) => (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') && close()}
  ></div>
  <div class="confirm-panel" on:pointerdown|stopPropagation>
    <div class="confirm-title">{title}</div>
    <div class="confirm-message">{message}</div>
    <div class="confirm-actions">
      <button class="btn ghost" on:click={close}>{cancelLabel}</button>
      <button class="btn danger" on:click={confirmAction}>{confirmLabel}</button>
    </div>
  </div>
{/if}

<style>
  .confirm-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.35);
    z-index: 90;
  }

  .confirm-panel {
    position: fixed;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    width: min(28rem, calc(100vw - 2rem));
    background: #000;
    color: var(--fg);
    border: 1px solid rgba(232, 232, 232, 0.25);
    border-radius: 10px;
    padding: 0.9rem;
    z-index: 91;
  }

  .confirm-title {
    font-size: 0.95rem;
    font-weight: 700;
    margin-bottom: 0.35rem;
  }

  .confirm-message {
    font-size: 0.85rem;
    opacity: 0.82;
    line-height: 1.4;
    white-space: pre-wrap;
  }

  .confirm-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.45rem;
    margin-top: 0.8rem;
  }

  .btn {
    border: 1px solid rgba(232, 232, 232, 0.35);
    background: none;
    color: var(--fg);
    border-radius: 6px;
    padding: 0.35rem 0.65rem;
    font-size: 0.8rem;
    cursor: pointer;
  }

  .btn.ghost {
    opacity: 0.85;
  }

  .btn.danger {
    border-color: rgba(255, 120, 120, 0.5);
    color: #ff9a9a;
  }

  :global([data-theme='nightly']) .confirm-panel {
    border-color: rgba(200, 0, 0, 0.5);
  }

  :global([data-theme='nightly']) .btn {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
  }

  :global([data-theme='nightly']) .btn.danger {
    border-color: rgba(200, 0, 0, 0.8);
    color: #ff0000;
  }
</style>
