<script>
  export let size = '1em'
</script>

<svg
  viewBox="0 0 24 24"
  width={size}
  height={size}
  fill="none"
  stroke="currentColor"
  stroke-width="1.4"
  stroke-linecap="round"
  {...$$restProps}
>
  <circle cx="12" cy="12" r="9" />
  <circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none" />
  <line x1="12" y1="1" x2="12" y2="3.5" />
  <line x1="12" y1="20.5" x2="12" y2="23" />
  <line x1="1" y1="12" x2="3.5" y2="12" />
  <line x1="20.5" y1="12" x2="23" y2="12" />
</svg>
