<script>
  export let progressPct = 0
  $: bounded = Math.max(0, Math.min(100, Number(progressPct) || 0))
</script>

<div class="quiz-progress" aria-label="Quiz progress">
  <div class="track">
    <div class="fill" style={`width:${bounded}%`}></div>
  </div>
  <span class="txt">{bounded.toFixed(0)}%</span>
</div>

<style>
  .quiz-progress {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .track {
    height: 8px;
    flex: 1;
    border-radius: 999px;
    background: rgba(180, 0, 0, 0.22);
    overflow: hidden;
  }

  .fill {
    height: 100%;
    border-radius: inherit;
    background: rgba(0, 0, 200, 0.78);
    transition: width 120ms linear;
  }

  .txt {
    color: var(--fg);
    font-size: 0.82rem;
    min-width: 2.2rem;
    text-align: right;
  }
</style>
