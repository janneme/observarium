<script>
  export let kind = 'generic'

  const solarGlyph = {
    sun: '☉',
    moon: '☽',
    mercury: '☿',
    venus: '♀',
    mars: '♂',
    jupiter: '♃',
    saturn: '♄',
    uranus: '♅',
    neptune: '♆',
    pluto: '♇',
  }

  function isSolar(k) {
    return Object.prototype.hasOwnProperty.call(solarGlyph, k)
  }
</script>

<span class="symbol" aria-hidden="true">
  {#if kind === 'open_cluster'}
    <svg viewBox="0 0 20 20" class="svg" fill="none">
      <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 3" />
    </svg>
  {:else if kind === 'globular_cluster'}
    <svg viewBox="0 0 20 20" class="svg" fill="none">
      <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5" />
      <path d="M3 10h14M10 3v14" stroke="currentColor" stroke-width="1.5" />
    </svg>
  {:else if kind === 'planetary_nebula'}
    <svg viewBox="0 0 20 20" class="svg" fill="none">
      <circle cx="10" cy="10" r="6" stroke="currentColor" stroke-width="1.5" />
      <path d="M1.5 10H4M16 10h2.5M10 1.5V4M10 16v2.5" stroke="currentColor" stroke-width="1.5" />
    </svg>
  {:else if kind === 'galaxy'}
    <svg viewBox="0 0 20 20" class="svg" fill="none">
      <ellipse cx="10" cy="10" rx="7" ry="3.5" stroke="currentColor" stroke-width="1.5" />
    </svg>
  {:else if kind === 'dark_nebula'}
    <svg viewBox="0 0 20 20" class="svg" fill="none">
      <rect x="3" y="3" width="14" height="14" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 3" />
    </svg>
  {:else if kind === 'galaxy_cluster'}
    <svg viewBox="0 0 20 20" class="svg" fill="none">
      <path d="M10 2.5L17 7.6L14.3 15.8H5.7L3 7.6Z" stroke="currentColor" stroke-width="1.5" />
    </svg>
  {:else if kind === 'quasar'}
    <svg viewBox="0 0 20 20" class="svg" fill="none">
      <path d="M4 4l12 12M16 4L4 16" stroke="currentColor" stroke-width="1.5" />
    </svg>
  {:else if kind === 'nebula'}
    <svg viewBox="0 0 20 20" class="svg" fill="none">
      <rect x="3" y="3" width="14" height="14" stroke="currentColor" stroke-width="1.5" />
    </svg>
  {:else if kind === 'double_star'}
    <span class="glyph">⊛</span>
  {:else if kind === 'star'}
    <span class="glyph">★</span>
  {:else if isSolar(kind)}
    <span class="glyph">{solarGlyph[kind]}</span>
  {:else}
    <span class="glyph">◉</span>
  {/if}
</span>

<style>
  .symbol {
    width: 1rem;
    height: 1rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }

  .svg {
    width: 1rem;
    height: 1rem;
    display: block;
  }

  .glyph {
    font-size: 0.9rem;
  }
</style>
