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
  <circle cx="10" cy="14" r="5" />
  <ellipse cx="10" cy="14" rx="9.5" ry="3" transform="rotate(-15 10 14)" />
  <path d="M19 3 Q21 3 21 5 Q21 6.5 19.5 6.5 L19.5 8" stroke-width="1.3" />
  <circle cx="19.5" cy="9.5" r="0.75" fill="currentColor" stroke="none" />
</svg>
