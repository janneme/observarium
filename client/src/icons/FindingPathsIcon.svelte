<script>
  export let size = '28px'
</script>

<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  width={size}
  height={size}
  style="display:block"
  {...$$restProps}
>
  <circle cx="5" cy="5" r="2" />
  <circle cx="19" cy="5" r="2" />
  <circle cx="5" cy="19" r="2" />
  <path d="M7 5h7a4 4 0 0 1 4 4v0" />
  <path d="M19 9v1a9 9 0 0 1-9 9H7" />
</svg>
