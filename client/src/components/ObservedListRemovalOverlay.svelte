<script>
  import { createEventDispatcher } from 'svelte'
  import CustomCheckbox from './CustomCheckbox.svelte'

  // One row per ACTIVE list containing the object being marked Observed
  // (lists.md §5). Each item: { id, name, count }.
  export let lists = []

  const dispatch = createEventDispatcher()

  let toggled = new Set()

  function toggle(id) {
    const next = new Set(toggled)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    toggled = next
  }

  function remove() {
    dispatch('remove', { listIds: [...toggled] })
  }

  function continueWithoutRemoving() {
    dispatch('continue')
  }
</script>

<div class="backdrop" on:pointerdown|stopPropagation></div>
<div class="panel" on:pointerdown|stopPropagation>
  <div class="title">This object is present in some active lists. Would you like to remove it from these lists?</div>
  <div class="list-rows">
    {#each lists as list (list.id)}
      <div class="list-row">
        <span class="list-label">{list.name} ({list.count})</span>
        <CustomCheckbox checked={toggled.has(list.id)} on:change={() => toggle(list.id)} />
      </div>
    {/each}
  </div>
  <div class="actions">
    <button class="btn ghost" type="button" on:click={continueWithoutRemoving}>Continue without removing</button>
    <button class="btn" type="button" disabled={toggled.size === 0} on:click={remove}>Remove</button>
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

  .btn.ghost {
    opacity: 0.85;
  }

  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }

  :global([data-theme='nightly']) .panel {
    border-color: rgba(200, 0, 0, 0.5);
  }

  :global([data-theme='nightly']) .btn {
    border-color: rgba(200, 0, 0, 0.55);
    color: #ff0000;
  }
</style>
