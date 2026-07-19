<script>
  import { createEventDispatcher } from 'svelte'

  export let title = 'Quiz Setup'
  export let hasSaved = false
  export let initialDifficulty = 'medium'
  export let initialScope = 'global'
  // Some quizzes (e.g. Moon Quiz) only support Local scope from a certain
  // difficulty upward. When false, the Local button is disabled and scope
  // is forced back to 'global' — kept generic here (the calling quiz screen
  // decides the actual rule) so other quizzes are unaffected by default.
  export let allowLocal = true

  const dispatch = createEventDispatcher()
  let difficulty = initialDifficulty
  let scope = initialScope
  let prevInitialDifficulty = initialDifficulty
  let prevInitialScope = initialScope
  let prevAllowLocal = allowLocal

  $: if (initialDifficulty !== prevInitialDifficulty) {
    prevInitialDifficulty = initialDifficulty
    difficulty = initialDifficulty
  }

  $: if (initialScope !== prevInitialScope) {
    prevInitialScope = initialScope
    scope = initialScope
  }

  $: if (allowLocal !== prevAllowLocal) {
    prevAllowLocal = allowLocal
    if (!allowLocal && scope === 'local') {
      scope = 'global'
      dispatch('change', { difficulty, scope })
    }
  }

  function setScope(next) {
    if (next === 'local' && !allowLocal) return
    scope = next
    dispatch('change', { difficulty, scope })
  }

  function setDifficulty(next) {
    difficulty = next
    dispatch('change', { difficulty, scope })
  }

  function start(continuePrev = false) {
    dispatch('start', { difficulty, scope, continuePrev })
  }
</script>

<div class="quiz-setup" on:pointerdown|stopPropagation>
  <h2>{title}</h2>

  <div class="group">
    <div class="label">Scope</div>
    <div class="row">
      <button class:selected={scope === 'global'} on:click={() => setScope('global')}>Global</button>
      <button
        class:selected={scope === 'local'}
        disabled={!allowLocal}
        title={allowLocal ? '' : 'Not available at this difficulty'}
        on:click={() => setScope('local')}>Local</button
      >
    </div>
  </div>

  <div class="group">
    <div class="label">Difficulty</div>
    <div class="row">
      <button class:selected={difficulty === 'easy'} on:click={() => setDifficulty('easy')}>Easy</button>
      <button class:selected={difficulty === 'medium'} on:click={() => setDifficulty('medium')}>Medium</button>
      <button class:selected={difficulty === 'hard'} on:click={() => setDifficulty('hard')}>Hard</button>
    </div>
  </div>

  <div class="actions">
    {#if hasSaved}
      <button class="primary" on:click={() => start(true)}>Continue previous quiz</button>
    {/if}
    <button class="primary" on:click={() => start(false)}>Start new quiz</button>
  </div>
</div>

<style>
  .quiz-setup {
    border: 1px solid rgba(180, 0, 0, 0.45);
    border-radius: 10px;
    padding: 0.8rem;
    background: rgba(0, 0, 0, 0.82);
  }

  h2 {
    margin: 0 0 0.7rem;
    font-size: 1.2rem;
    color: var(--fg);
  }

  .group {
    margin-bottom: 0.7rem;
  }

  .label {
    color: rgba(200, 0, 0, 0.9);
    font-size: 1.032rem;
    margin-bottom: 0.35rem;
  }

  .row {
    display: flex;
    gap: 0.4rem;
  }

  .row button {
    border: 1px solid rgba(180, 0, 0, 0.45);
    background: rgba(0, 0, 0, 0.8);
    color: var(--fg);
    border-radius: 7px;
    padding: 0.36rem 0.6rem;
    font-size: 1.2rem;
    cursor: pointer;
  }

  .row button.selected {
    border-color: rgba(0, 0, 200, 0.85);
    box-shadow: 0 0 0 1px rgba(0, 0, 200, 0.6) inset;
  }

  .row button:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .actions {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .primary {
    border: 1px solid rgba(180, 0, 0, 0.45);
    background: rgba(200, 0, 0, 0.12);
    color: var(--fg);
    border-radius: 8px;
    padding: 0.45rem 0.7rem;
    font-size: 1.2rem;
    cursor: pointer;
  }

  .primary:hover {
    background: rgba(200, 0, 0, 0.2);
  }
</style>
