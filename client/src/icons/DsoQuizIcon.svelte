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
  <g style="color: #5a8fd4" opacity="0.6">
    <!-- Globular cluster (top-left) -->
    <circle cx="6" cy="6" r="3.5" stroke="currentColor" />
    <line x1="2.5" y1="6" x2="9.5" y2="6" stroke="currentColor" />
    <line x1="6" y1="2.5" x2="6" y2="9.5" stroke="currentColor" />
    <!-- Open cluster (top-right) -->
    <circle cx="18" cy="6" r="3.5" stroke="currentColor" stroke-dasharray="2 1.5" />
    <!-- Planetary nebula (bottom-left) -->
    <circle cx="6" cy="18" r="2.5" stroke="currentColor" />
    <line x1="2" y1="18" x2="4" y2="18" stroke="currentColor" />
    <line x1="8" y1="18" x2="10" y2="18" stroke="currentColor" />
    <line x1="6" y1="14" x2="6" y2="16" stroke="currentColor" />
    <line x1="6" y1="20" x2="6" y2="22" stroke="currentColor" />
    <!-- Galaxy (bottom-right) -->
    <ellipse cx="18" cy="18" rx="4.5" ry="1.8" stroke="currentColor" />
  </g>
  <text
    x="12"
    y="13"
    font-size="13"
    font-weight="700"
    text-anchor="middle"
    dominant-baseline="middle"
    fill="currentColor"
    stroke="none">?</text
  >
</svg>
