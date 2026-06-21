// Custom search aliases: lets users find objects by informal names not in the source catalogues.
// Keys are object IDs (matching those in the search index); values are arrays of alias strings.
export const SEARCH_ALIASES = {
  star_HIP91919: ['Double Double'], // ε¹ Lyr
  star_HIP91926: ['Double Double'], // ε² Lyr
}

// Patches applied on top of WDS double-star records at display time.
// Keyed by double_star object ID ('double_WDS' + wdsId).
const DS_PATCHES = {
  'double_WDS18443+3940': {
    spect: 'A4V+F1V+F0V+F0V',
    pairs: [
      { comp: 'AB', mag: [5.15, 6.1], sep: [2.1, 4.0], phys: 'AB' },
      { comp: 'CD', mag: [5.25, 5.38], sep: [2.0, 2.4], phys: 'CD' },
      { comp: 'AC', sep: 207.7 },
    ],
  },
}

export function applyDsPatch(ds) {
  if (!ds) return ds
  const patch = DS_PATCHES[ds.id]
  if (!patch) return ds
  return { ...ds, ...patch }
}
