import { describe, it, expect } from 'vitest'
import { parseBayerQuery, parseFlamsteedQuery, doSearch } from '../../src/lib/search.js'

// ── Minimal mock objects ──────────────────────────────────────────────────────

const eps1lyr = { id: 'star_eps1lyr', bay: 'ε¹', constellation: 'Lyr', name: 'Epsilon1 Lyrae' }
const eps2lyr = { id: 'star_eps2lyr', bay: 'ε²', constellation: 'Lyr', name: 'Epsilon2 Lyrae' }

const albireo = {
  id: 'star_95947',
  bay: 'β¹', // Beta¹ Cygni
  constellation: 'Cyg',
  name: 'Albireo',
  flam: 6,
  hip: 95947,
  hd: 183912,
}

const betelgeuse = {
  id: 'star_27989',
  bay: 'α',
  constellation: 'Ori',
  name: 'Betelgeuse',
  flam: 58,
  hip: 27989,
  hd: 39801,
}

const rigel = {
  id: 'star_24436',
  bay: 'β', // Beta Orionis — no superscript index
  constellation: 'Ori',
  name: 'Rigel',
  flam: 19,
  hip: 24436,
  hd: 34085,
}

const m42 = {
  id: 'dso_m42',
  constellation: 'Ori',
  name: 'Orion Nebula',
  m: 42,
  ngc: 1976,
}

const INDEX = [albireo, betelgeuse, rigel, m42]

// ── parseBayerQuery ───────────────────────────────────────────────────────────

describe('parseBayerQuery', () => {
  it('parses 3-letter abbreviation + abbreviation', () => {
    expect(parseBayerQuery('bet cyg')).toEqual({ greek: 'β', idx: null, con: 'cyg' })
  })

  it('parses full Greek name + abbreviation', () => {
    expect(parseBayerQuery('beta cyg')).toEqual({ greek: 'β', idx: null, con: 'cyg' })
  })

  it('parses abbreviated Greek + superscript digit', () => {
    expect(parseBayerQuery('bet1 cyg')).toEqual({ greek: 'β', idx: '¹', con: 'cyg' })
  })

  it('parses full Greek name + superscript digit', () => {
    expect(parseBayerQuery('beta1 cyg')).toEqual({ greek: 'β', idx: '¹', con: 'cyg' })
  })

  it('passes through genitive constellation name (raw)', () => {
    expect(parseBayerQuery('beta cygni')).toEqual({ greek: 'β', idx: null, con: 'cygni' })
  })

  it('passes through nominative constellation name (raw)', () => {
    expect(parseBayerQuery('beta cygnus')).toEqual({ greek: 'β', idx: null, con: 'cygnus' })
  })

  it('passes through genitive + digit (raw)', () => {
    expect(parseBayerQuery('beta1 cygni')).toEqual({ greek: 'β', idx: '¹', con: 'cygni' })
  })

  it('returns null for single-token query (no space)', () => {
    expect(parseBayerQuery('betacyg')).toBeNull()
  })

  it('returns null for unknown Greek letter', () => {
    expect(parseBayerQuery('xyz cyg')).toBeNull()
  })

  it('parses other Greek letters', () => {
    expect(parseBayerQuery('alp ori')).toEqual({ greek: 'α', idx: null, con: 'ori' })
    expect(parseBayerQuery('alpha orionis')).toEqual({ greek: 'α', idx: null, con: 'orionis' })
  })
})

// ── parseFlamsteedQuery ───────────────────────────────────────────────────────

describe('parseFlamsteedQuery', () => {
  it('parses number + abbreviation', () => {
    expect(parseFlamsteedQuery('6 cyg')).toEqual({ num: 6, con: 'cyg' })
  })

  it('passes through genitive constellation name (raw)', () => {
    expect(parseFlamsteedQuery('6 cygni')).toEqual({ num: 6, con: 'cygni' })
  })

  it('passes through nominative constellation name (raw)', () => {
    expect(parseFlamsteedQuery('58 orionis')).toEqual({ num: 58, con: 'orionis' })
  })

  it('returns null for non-numeric first token', () => {
    expect(parseFlamsteedQuery('bet cyg')).toBeNull()
  })
})

// ── doSearch — name queries ───────────────────────────────────────────────────

describe('doSearch — name', () => {
  it('finds Albireo by exact name', () => {
    const r = doSearch('Albireo', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('finds Albireo by case-insensitive prefix', () => {
    const r = doSearch('albi', INDEX)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('finds Albireo by name substring', () => {
    const r = doSearch('bireo', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('returns empty array for non-existent name', () => {
    expect(doSearch('Zorklon', INDEX)).toHaveLength(0)
  })
})

// ── doSearch — Bayer queries ──────────────────────────────────────────────────

describe('doSearch — Bayer', () => {
  it('finds Albireo by "bet cyg"', () => {
    const r = doSearch('bet cyg', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('finds Albireo by "beta cyg"', () => {
    const r = doSearch('beta cyg', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('finds Albireo by "beta1 cyg" (explicit superscript)', () => {
    const r = doSearch('beta1 cyg', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('finds Albireo by "bet1 cyg" (abbreviated + digit)', () => {
    const r = doSearch('bet1 cyg', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('finds Albireo by "beta cygni" (genitive)', () => {
    const r = doSearch('beta cygni', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('finds Albireo by "beta cygnus" (nominative)', () => {
    const r = doSearch('beta cygnus', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('does NOT find Albireo when superscript index does not match', () => {
    const r = doSearch('beta2 cyg', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(false)
  })

  it('finds Rigel (no superscript) by "beta ori"', () => {
    const r = doSearch('beta ori', INDEX)
    expect(r.some((x) => x.obj.id === 'star_24436')).toBe(true)
  })

  it('finds Betelgeuse by "alp ori"', () => {
    const r = doSearch('alp ori', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_27989')
  })

  it('display label includes Bayer + constellation', () => {
    const r = doSearch('bet cyg', INDEX)
    expect(r[0].display).toContain('β¹')
    expect(r[0].display).toContain('Cyg')
  })

  it('finds Albireo by partial abbreviation "bet c" (incremental)', () => {
    const r = doSearch('bet c', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('finds Albireo by "beta cy" (partial abbreviation prefix)', () => {
    const r = doSearch('beta cy', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('finds Albireo by "beta cygn" (partial genitive prefix)', () => {
    const r = doSearch('beta cygn', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('"bet c" does not match Rigel (β Ori — "c" is not a prefix of "ori")', () => {
    const r = doSearch('bet c', INDEX)
    expect(r.some((x) => x.obj.id === 'star_24436')).toBe(false)
  })

  it('orders ε¹ before ε² when searching "eps lyr" (no digit)', () => {
    const r = doSearch('eps lyr', [eps2lyr, eps1lyr]) // deliberately reversed in index
    expect(r[0].obj.id).toBe('star_eps1lyr')
    expect(r[1].obj.id).toBe('star_eps2lyr')
  })

  it('orders stars with no superscript before superscripted ones', () => {
    const plain = { id: 'star_plain', bay: 'β', constellation: 'Ori', name: 'Beta Orionis' }
    const sup1 = { id: 'star_sup1', bay: 'β¹', constellation: 'Ori', name: 'Beta1 Orionis' }
    const r = doSearch('beta ori', [sup1, plain])
    expect(r[0].obj.id).toBe('star_plain')
    expect(r[1].obj.id).toBe('star_sup1')
  })
})

// ── doSearch — Flamsteed queries ──────────────────────────────────────────────

describe('doSearch — Flamsteed', () => {
  it('finds Albireo by "6 cyg"', () => {
    const r = doSearch('6 cyg', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('finds Albireo by "6 cygni"', () => {
    const r = doSearch('6 cygni', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_95947')
  })

  it('finds Betelgeuse by "58 ori"', () => {
    const r = doSearch('58 ori', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_27989')
  })

  it('finds Betelgeuse by "58 orionis"', () => {
    const r = doSearch('58 orionis', INDEX)
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_27989')
  })

  it('does not match wrong Flamsteed number', () => {
    expect(doSearch('7 cyg', INDEX).some((x) => x.obj.id === 'star_95947')).toBe(false)
  })

  it('finds Albireo by "6 c" (partial abbreviation prefix)', () => {
    const r = doSearch('6 c', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('finds Albireo by "6 cygn" (partial genitive prefix)', () => {
    const r = doSearch('6 cygn', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })
})

// ── doSearch — custom alias queries ──────────────────────────────────────────

const doubleMock = {
  id: 'star_HIP91919',
  bay: 'ε¹',
  constellation: 'Lyr',
  aliases: ['Double Double'],
}

describe('doSearch — custom aliases', () => {
  it('finds object by full alias', () => {
    const r = doSearch('double double', [doubleMock])
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_HIP91919')
  })

  it('finds object by alias prefix', () => {
    const r = doSearch('double d', [doubleMock])
    expect(r).toHaveLength(1)
    expect(r[0].obj.id).toBe('star_HIP91919')
  })

  it('display contains alias and catalog label', () => {
    const r = doSearch('double double', [doubleMock])
    expect(r[0].display).toBe('Double Double, ε¹ Lyr')
  })

  it('alias match does not appear twice if already added via name', () => {
    const named = { id: 'star_test', name: 'Double Double', constellation: 'Lyr', aliases: ['Double Double'] }
    const r = doSearch('double double', [named])
    expect(r.filter((x) => x.obj.id === 'star_test')).toHaveLength(1)
  })

  it('ε¹ sorts before ε² even when index order is reversed', () => {
    const eps1 = { id: 'star_HIP91919', bay: 'ε¹', constellation: 'Lyr', aliases: ['Double Double'] }
    const eps2 = { id: 'star_HIP91926', bay: 'ε²', constellation: 'Lyr', aliases: ['Double Double'] }
    const r = doSearch('double double', [eps2, eps1])
    expect(r[0].obj.id).toBe('star_HIP91919')
    expect(r[1].obj.id).toBe('star_HIP91926')
  })
})

// ── doSearch — catalog token queries ─────────────────────────────────────────

describe('doSearch — HIP / HD', () => {
  it('finds Albireo by exact "HIP 95947"', () => {
    const r = doSearch('HIP 95947', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('finds Albireo by lowercase "hip 95947"', () => {
    const r = doSearch('hip 95947', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('finds Albireo by partial "hip 9594" prefix', () => {
    const r = doSearch('hip 9594', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('finds Albireo by "HD 183912"', () => {
    const r = doSearch('HD 183912', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('finds Albireo by partial "hd 1839" prefix', () => {
    const r = doSearch('hd 1839', INDEX)
    expect(r.some((x) => x.obj.id === 'star_95947')).toBe(true)
  })

  it('does not return a result for wrong HIP number', () => {
    expect(doSearch('hip 00001', INDEX)).toHaveLength(0)
  })
})

describe('doSearch — Messier / NGC', () => {
  it('finds Orion Nebula by "M 42"', () => {
    const r = doSearch('M 42', INDEX)
    expect(r.some((x) => x.obj.id === 'dso_m42')).toBe(true)
  })

  it('finds Orion Nebula by bare number "42"', () => {
    const r = doSearch('42', INDEX)
    expect(r.some((x) => x.obj.id === 'dso_m42')).toBe(true)
  })

  it('finds Orion Nebula by "NGC 1976"', () => {
    const r = doSearch('NGC 1976', INDEX)
    expect(r.some((x) => x.obj.id === 'dso_m42')).toBe(true)
  })
})

// ── doSearch — edge cases ─────────────────────────────────────────────────────

describe('doSearch — edge cases', () => {
  it('returns [] for null index', () => {
    expect(doSearch('albireo', null)).toEqual([])
  })

  it('returns [] for empty query', () => {
    expect(doSearch('', INDEX)).toEqual([])
  })

  it('returns [] for whitespace-only query', () => {
    expect(doSearch('   ', INDEX)).toEqual([])
  })

  it('deduplicates: name-matched Albireo not repeated in Bayer pass', () => {
    const r = doSearch('Albireo', INDEX)
    const ids = r.map((x) => x.obj.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('caps results at 20', () => {
    const big = Array.from({ length: 30 }, (_, i) => ({
      id: `star_${i}`,
      name: `Teststar ${i}`,
      constellation: 'Ori',
    }))
    expect(doSearch('teststar', big).length).toBe(20)
  })
})
