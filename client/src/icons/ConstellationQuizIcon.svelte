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
  <circle cx="4" cy="8" r="1.8" fill="currentColor" stroke="none" />
  <circle cx="13" cy="4" r="1.5" fill="currentColor" stroke="none" />
  <circle cx="19" cy="10" r="1.5" fill="currentColor" stroke="none" />
  <circle cx="14" cy="17" r="1.5" fill="currentColor" stroke="none" />
  <line x1="4" y1="8" x2="13" y2="4" />
  <line x1="13" y1="4" x2="19" y2="10" />
  <line x1="19" y1="10" x2="14" y2="17" />
  <path d="M4 19 Q5.5 17.5 7 18.5 Q8 19.5 7 20.5 L6.5 21.5" stroke-width="1.3" />
  <circle cx="6.5" cy="22.5" r="0.75" fill="currentColor" stroke="none" />
</svg>
