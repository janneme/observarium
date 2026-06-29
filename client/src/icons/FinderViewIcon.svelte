<script>
  export let size = '1em'
</script>
<svg
  viewBox="0 0 24 24"
  width={size}
  height={size}
  fill="none"
  stroke="currentColor"
  stroke-width="1.5"
  stroke-linecap="round"
  {...$$restProps}
>
  <circle cx="8" cy="14" r="4.5" />
  <circle cx="16" cy="14" r="4.5" />
  <path d="M8 9.5 L8 7" />
  <path d="M16 9.5 L16 7" />
  <path d="M8 7 Q12 5 16 7" />
  <line x1="11" y1="14" x2="13" y2="14" stroke-width="1.2" />
</svg>
