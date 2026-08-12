// Natural/intelligent string sort — e.g. "NGC 1" before "NGC 10" (a plain
// string compare would put "NGC 10" first). Splits into alternating
// number/non-number runs and compares numbers numerically.

function naturalSortKey(s) {
  const parts = []
  const re = /(\d+)|(\D+)/g
  let m
  while ((m = re.exec(String(s))) !== null) {
    if (m[1] != null) parts.push(parseInt(m[1], 10))
    else parts.push(m[2])
  }
  return parts
}

export function naturalCompare(strA, strB) {
  const ka = naturalSortKey(strA)
  const kb = naturalSortKey(strB)
  const len = Math.min(ka.length, kb.length)
  for (let i = 0; i < len; i++) {
    const ai = ka[i],
      bi = kb[i]
    if (typeof ai === 'number' && typeof bi === 'number') {
      if (ai !== bi) return ai - bi
    } else if (typeof ai === 'string' && typeof bi === 'string') {
      if (ai !== bi) return ai < bi ? -1 : 1
    } else {
      return typeof ai === 'number' ? -1 : 1
    }
  }
  return ka.length - kb.length
}
