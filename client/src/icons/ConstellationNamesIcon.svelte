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
  <line x1="8" y1="9" x2="13" y2="11" stroke-linecap="round" stroke-width="1.2" stroke-dasharray="1.5 1.5" />
  <text x="12" y="6" font-size="6" text-anchor="middle" fill="currentColor" stroke="none" style="font-style:italic">α</text>
</svg>
