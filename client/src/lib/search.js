// Lowercase Latin name / abbreviation → Unicode Greek letter
export const GREEK_NAMES = {
  alp: 'α',
  alpha: 'α',
  bet: 'β',
  beta: 'β',
  gam: 'γ',
  gamma: 'γ',
  del: 'δ',
  delta: 'δ',
  eps: 'ε',
  epsilon: 'ε',
  zet: 'ζ',
  zeta: 'ζ',
  eta: 'η',
  the: 'θ',
  theta: 'θ',
  iot: 'ι',
  iota: 'ι',
  kap: 'κ',
  kappa: 'κ',
  lam: 'λ',
  lambda: 'λ',
  mu: 'μ',
  nu: 'ν',
  xi: 'ξ',
  omi: 'ο',
  omicron: 'ο',
  pi: 'π',
  rho: 'ρ',
  sig: 'σ',
  sigma: 'σ',
  tau: 'τ',
  ups: 'υ',
  upsilon: 'υ',
  phi: 'φ',
  chi: 'χ',
  psi: 'ψ',
  ome: 'ω',
  omega: 'ω',
}

export const DIGIT_TO_SUP = {
  1: '¹',
  2: '²',
  3: '³',
  4: '⁴',
  5: '⁵',
  6: '⁶',
  7: '⁷',
  8: '⁸',
  9: '⁹',
}

// Reverse map: superscript → numeric value for sorting (¹ < ² < …)
// Unicode code points for ¹²³ are not in natural order, so we can't use charCodeAt.
export const SUP_TO_DIGIT = { '¹': 1, '²': 2, '³': 3, '⁴': 4, '⁵': 5, '⁶': 6, '⁷': 7, '⁸': 8, '⁹': 9 }

// Maps full constellation names (nominative and genitive) to IAU 3-letter abbreviations.
// This lets users type "beta cygni" or "beta cygnus" in addition to "bet cyg".
// Multi-word constellations (Ursa Major, Canis Minor, etc.) are not supported here
// because the Bayer/Flamsteed query parser only captures a single trailing word.
export const CON_ALIASES = {
  andromeda: 'and',
  andromedae: 'and',
  antlia: 'ant',
  antliae: 'ant',
  apus: 'aps',
  apodis: 'aps',
  aquila: 'aql',
  aquilae: 'aql',
  aquarius: 'aqr',
  aquarii: 'aqr',
  ara: 'ara',
  arae: 'ara',
  aries: 'ari',
  arietis: 'ari',
  auriga: 'aur',
  aurigae: 'aur',
  bootes: 'boo',
  bootis: 'boo',
  caelum: 'cae',
  caeli: 'cae',
  camelopardalis: 'cam',
  capricornus: 'cap',
  capricorni: 'cap',
  carina: 'car',
  carinae: 'car',
  cassiopeia: 'cas',
  cassiopeiae: 'cas',
  centaurus: 'cen',
  centauri: 'cen',
  cepheus: 'cep',
  cephei: 'cep',
  cetus: 'cet',
  ceti: 'cet',
  chamaeleon: 'cha',
  chamaeleontis: 'cha',
  circinus: 'cir',
  circini: 'cir',
  cancer: 'cnc',
  cancri: 'cnc',
  columba: 'col',
  columbae: 'col',
  crater: 'crt',
  crateris: 'crt',
  crux: 'cru',
  crucis: 'cru',
  corvus: 'crv',
  corvi: 'crv',
  cygnus: 'cyg',
  cygni: 'cyg',
  delphinus: 'del',
  delphini: 'del',
  dorado: 'dor',
  doradus: 'dor',
  draco: 'dra',
  draconis: 'dra',
  equuleus: 'equ',
  equulei: 'equ',
  eridanus: 'eri',
  eridani: 'eri',
  fornax: 'for',
  fornacis: 'for',
  gemini: 'gem',
  geminorum: 'gem',
  grus: 'gru',
  gruis: 'gru',
  hercules: 'her',
  herculis: 'her',
  horologium: 'hor',
  horologii: 'hor',
  hydra: 'hya',
  hydrae: 'hya',
  hydrus: 'hyi',
  hydri: 'hyi',
  indus: 'ind',
  indi: 'ind',
  lacerta: 'lac',
  lacertae: 'lac',
  leo: 'leo',
  leonis: 'leo',
  lepus: 'lep',
  leporis: 'lep',
  libra: 'lib',
  librae: 'lib',
  lupus: 'lup',
  lupi: 'lup',
  lynx: 'lyn',
  lyncis: 'lyn',
  lyra: 'lyr',
  lyrae: 'lyr',
  mensa: 'men',
  mensae: 'men',
  microscopium: 'mic',
  microscopii: 'mic',
  monoceros: 'mon',
  monocerotis: 'mon',
  musca: 'mus',
  muscae: 'mus',
  norma: 'nor',
  normae: 'nor',
  octans: 'oct',
  octantis: 'oct',
  ophiuchus: 'oph',
  ophiuchi: 'oph',
  orion: 'ori',
  orionis: 'ori',
  pavo: 'pav',
  pavonis: 'pav',
  pegasus: 'peg',
  pegasi: 'peg',
  perseus: 'per',
  persei: 'per',
  phoenix: 'phe',
  phoenicis: 'phe',
  pictor: 'pic',
  pictoris: 'pic',
  pisces: 'psc',
  piscium: 'psc',
  puppis: 'pup',
  pyxis: 'pyx',
  pyxidis: 'pyx',
  reticulum: 'ret',
  reticuli: 'ret',
  sculptor: 'scl',
  sculptoris: 'scl',
  scorpius: 'sco',
  scorpii: 'sco',
  scutum: 'sct',
  scuti: 'sct',
  serpens: 'ser',
  serpentis: 'ser',
  sextans: 'sex',
  sextantis: 'sex',
  sagitta: 'sge',
  sagittae: 'sge',
  sagittarius: 'sgr',
  sagittarii: 'sgr',
  taurus: 'tau',
  tauri: 'tau',
  telescopium: 'tel',
  telescopii: 'tel',
  triangulum: 'tri',
  trianguli: 'tri',
  tucana: 'tuc',
  tucanae: 'tuc',
  vela: 'vel',
  velorum: 'vel',
  virgo: 'vir',
  virginis: 'vir',
  volans: 'vol',
  volantis: 'vol',
  vulpecula: 'vul',
  vulpeculae: 'vul',
}

// Check whether `typed` (the raw constellation token from the query) matches a
// stored IAU 3-letter abbreviation `objCon`.  Two cases are accepted:
//   1. Abbreviation prefix — "c", "cy", "cyg" all match "Cyg".
//   2. Full/genitive-name prefix — "cygn" or "cygni" match "Cyg" via CON_ALIASES.
// This lets the user get results as they type, not only after the full name.
function matchesCon(typed, objCon) {
  const objLow = objCon.toLowerCase()
  if (objLow.startsWith(typed)) return true
  for (const [alias, abbrev] of Object.entries(CON_ALIASES)) {
    if (alias.startsWith(typed) && abbrev === objLow) return true
  }
  return false
}

// Parse "beta1 cyg" → { greek: 'β', idx: '¹', con: 'cyg' }
// idx is null when omitted (matches any superscript index).
// con is the raw typed token — matching uses matchesCon() for prefix/alias support.
export function parseBayerQuery(q) {
  const m = q.match(/^([a-z]+)(\d*)\s+([a-z]+)$/)
  if (!m) return null
  const greek = GREEK_NAMES[m[1]]
  if (!greek) return null
  return { greek, idx: m[2] ? (DIGIT_TO_SUP[m[2]] ?? null) : null, con: m[3] }
}

// Parse "6 cyg" → { num: 6, con: 'cyg' }
// con is the raw typed token — matching uses matchesCon() for prefix/alias support.
export function parseFlamsteedQuery(q) {
  const m = q.match(/^(\d+)\s+([a-z]+)$/)
  if (!m) return null
  return { num: parseInt(m[1], 10), con: m[2] }
}

// Split display string into plain/highlighted spans for rendering
export function makeSpans(display, start, end) {
  if (start == null || start >= end) return [{ text: display, hl: false }]
  const spans = []
  if (start > 0) spans.push({ text: display.slice(0, start), hl: false })
  spans.push({ text: display.slice(start, end), hl: true })
  if (end < display.length) spans.push({ text: display.slice(end), hl: false })
  return spans
}

// Build searchable catalogue tokens for an object.
// Bare numeric tokens are included for Messier/NGC/IC/Caldwell so that
// searching "31" finds M31, "224" finds NGC 224, etc.
// HIP/HD are prefix-only to avoid noise from thousands of bare numbers.
export function catEntries(obj) {
  const cats = []
  if (obj.m != null) {
    const n = String(obj.m)
    cats.push({ label: `M ${obj.m}`, tokens: [`m${n}`, n] })
  }
  if (obj.ngc != null) {
    const n = String(obj.ngc)
    cats.push({ label: `NGC ${obj.ngc}`, tokens: [`ngc${n}`, n] })
  }
  if (obj.ic != null) {
    const n = String(obj.ic)
    cats.push({ label: `IC ${obj.ic}`, tokens: [`ic${n}`, n] })
  }
  if (obj.caldwell != null) {
    const n = String(obj.caldwell)
    cats.push({ label: `C ${obj.caldwell}`, tokens: [`c${n}`, `caldwell${n}`] })
  }
  if (obj.hip != null) {
    cats.push({ label: `HIP ${obj.hip}`, tokens: [`hip${String(obj.hip)}`] })
  }
  if (obj.hd != null) {
    cats.push({ label: `HD ${obj.hd}`, tokens: [`hd${String(obj.hd)}`] })
  }
  return cats
}

export function doSearch(q, searchIndex) {
  if (!searchIndex) return []
  const trimmed = q.trim()
  if (!trimmed) return []
  // nq: space-stripped lowercase (used for name and token matching)
  const nq = trimmed.toLowerCase().replace(/\s+/g, '')
  // qLow: space-normalised lowercase (used for Bayer/Flamsteed pattern parsing)
  const qLow = trimmed.toLowerCase().replace(/\s+/g, ' ')

  const out = []
  const seen = new Set()

  // showCon: whether to append " (constellation)" after the display label.
  // False for Bayer/Flamsteed results where the constellation is already
  // embedded in the catalogue label (e.g. "β¹ Cyg").
  function add(obj, display, hlStart, hlEnd, showCon) {
    if (seen.has(obj.id)) return
    seen.add(obj.id)
    out.push({ obj, display, spans: makeSpans(display, hlStart, hlEnd), showCon })
  }

  // Pass 0: prefix match on proper name or custom alias (highest rank)
  for (const obj of searchIndex) {
    if (obj.name && obj.name.toLowerCase().replace(/\s+/g, '').startsWith(nq)) {
      add(obj, obj.name, 0, nq.length, true)
    } else if (obj.aliases) {
      for (const alias of obj.aliases) {
        if (seen.has(obj.id)) break
        if (alias.toLowerCase().replace(/\s+/g, '').startsWith(nq)) {
          const catLabel = obj.bay && obj.constellation ? `, ${obj.bay} ${obj.constellation}` : ''
          const display = alias + catLabel
          add(obj, display, 0, alias.length, false)
          break
        }
      }
    }
  }

  // Pass 1: Bayer designation match ("bet cyg", "beta1 cyg", "bet c", …)
  const bayer = parseBayerQuery(qLow)
  if (bayer) {
    const bayerMatches = []
    for (const obj of searchIndex) {
      if (seen.has(obj.id) || !obj.bay || !obj.constellation) continue
      if (!matchesCon(bayer.con, obj.constellation)) continue
      if (obj.bay[0] !== bayer.greek) continue
      const objIdx = obj.bay.length > 1 ? obj.bay.slice(1) : ''
      if (bayer.idx !== null && objIdx !== bayer.idx) continue
      bayerMatches.push({ obj, objIdx })
    }
    // Sort: no superscript first (0), then ¹ < ² < … (Unicode order is wrong, use SUP_TO_DIGIT)
    bayerMatches.sort((a, b) => (SUP_TO_DIGIT[a.objIdx] ?? 0) - (SUP_TO_DIGIT[b.objIdx] ?? 0))
    for (const { obj } of bayerMatches) {
      const catLabel = `${obj.bay} ${obj.constellation}`
      const display = obj.name ? `${obj.name}, ${catLabel}` : catLabel
      const hlStart = obj.name ? obj.name.length + 2 : 0
      add(obj, display, hlStart, display.length, false)
    }
  }

  // Pass 2: Flamsteed designation match ("6 cyg", "6 c", …)
  const flam = parseFlamsteedQuery(qLow)
  if (flam) {
    for (const obj of searchIndex) {
      if (seen.has(obj.id) || obj.flam == null || !obj.constellation) continue
      if (obj.flam !== flam.num || !matchesCon(flam.con, obj.constellation)) continue
      const catLabel = `${obj.flam} ${obj.constellation}`
      const display = obj.name ? `${obj.name}, ${catLabel}` : catLabel
      const hlStart = obj.name ? obj.name.length + 2 : 0
      add(obj, display, hlStart, display.length, false)
    }
  }

  // Pass 3: prefix match on catalogue number token (HIP, HD, M, NGC, …)
  for (const obj of searchIndex) {
    if (seen.has(obj.id)) continue
    for (const cat of catEntries(obj)) {
      if (cat.tokens.some((t) => t.startsWith(nq))) {
        const display = obj.name ? `${obj.name}, ${cat.label}` : cat.label
        const hlStart = obj.name ? obj.name.length + 2 : 0
        add(obj, display, hlStart, display.length, true)
        break
      }
    }
  }

  // Pass 4: substring match on proper name (lowest rank)
  for (const obj of searchIndex) {
    if (seen.has(obj.id) || !obj.name) continue
    const lower = obj.name.toLowerCase().replace(/\s+/g, '')
    const idx = lower.indexOf(nq)
    if (idx !== -1) add(obj, obj.name, idx, idx + nq.length, true)
  }

  // Sort alphabetically by display string; normalize superscript digits (¹²³…) to
  // their ASCII equivalents so ε¹ < ε² instead of the reverse (U+00B9 > U+00B2).
  out.sort((a, b) => {
    const norm = (s) => s.replace(/[¹²³⁴⁵⁶⁷⁸⁹]/g, (c) => String(SUP_TO_DIGIT[c] ?? c))
    return norm(a.display).localeCompare(norm(b.display))
  })

  return out.slice(0, 20)
}
