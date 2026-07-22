<script>
  export let size = '1em'
  // true: full disc (no terminator). false: partial phase (terminator-cropped).
  export let full = false
</script>

<svg viewBox="0 0 24 24" width={size} height={size} {...$$restProps}>
  <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6" />
  {#if full}
    <circle cx="12" cy="12" r="9" fill="currentColor" />
  {:else}
    <path d="M12 3a9 9 0 0 0 0 18 6 9 0 0 1 0-18Z" fill="currentColor" />
  {/if}
</svg>
