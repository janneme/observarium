<script>
  import { createEventDispatcher } from 'svelte'
  import CustomCheckbox from './CustomCheckbox.svelte'

  // One row per list (active or not), for freely managing an object's list
  // membership from "About object" (lists.md §6). Each item:
  // { id, name, count, active, member }.
  export let lists = []

  const dispatch = createEventDispatcher()

  function toggle(list) {
    dispatch('toggle', { listId: list.id, member: !list.member })
  }

  function close() {
    dispatch('close')
  }
</script>

<div
  class="backdrop"
  role="button"
  tabindex="0"
  aria-label="Close"
  on:pointerdown|stopPropagation
  on:click={close}
  on:keydown={(e) => (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') && close()}
></div>
<div class="panel" on:pointerdown|stopPropagation>
  <div class="title">Include object in some lists?</div>
  <div class="list-rows">
    {#each lists as list (list.id)}
      <div class="list-row">
        <span class="list-label" class:active={list.active}>{list.name} ({list.count})</span>
        <CustomCheckbox checked={list.member} on:change={() => toggle(list)} />
      </div>
    {/each}
  </div>
  <div class="actions">
    <button class="btn" type="button" on:click={close}>Close</button>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.35);
    z-index: 90;
  }

  .panel {
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

  .title {
    font-size: 0.9rem;
    line-height: 1.4;
    margin-bottom: 0.6rem;
  }

  .list-rows {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-bottom: 0.7rem;
  }

  .list-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .list-label {
    font-size: 0.88rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .list-label.active {
    font-weight: 700;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.45rem;
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

  :global([data-theme='nightly']) .panel {
    border-color: rgba(200, 0, 0, 0.5);
  }

  :global([data-theme='nightly']) .btn {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
  }
</style>
