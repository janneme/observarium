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
  {...$$restProps}
>
  <circle cx="4" cy="6" r="2" fill="currentColor" stroke="none" />
  <circle cx="20" cy="8" r="1.6" fill="currentColor" stroke="none" />
  <circle cx="14" cy="19" r="1.6" fill="currentColor" stroke="none" />
  <line x1="4" y1="6" x2="20" y2="8" stroke-linecap="round" />
  <line x1="20" y1="8" x2="14" y2="19" stroke-linecap="round" />
  <line x1="4" y1="6" x2="14" y2="19" stroke-linecap="round" />
</svg>
