const CORRECT_DELTA = 0.25
const WRONG_DELTA = 0.5

export function quizStorageKey(type, difficulty, scope) {
  return `quiz_${type}_${difficulty}_${scope}`
}

export function loadQuizState(type, difficulty, scope) {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(quizStorageKey(type, difficulty, scope))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed.pool) || typeof parsed.mastery !== 'object') return null
    return parsed
  } catch {
    return null
  }
}

export function saveQuizState(type, difficulty, scope, state) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(quizStorageKey(type, difficulty, scope), JSON.stringify(state))
  } catch {
    return
  }
}

export function clearQuizState(type, difficulty, scope) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(quizStorageKey(type, difficulty, scope))
  } catch {
    return
  }
}

export function computeProgressPct(pool, mastery) {
  if (!Array.isArray(pool) || pool.length === 0) return 0
  let acc = 0
  for (const id of pool) {
    const v = Number(mastery?.[id] ?? 0)
    acc += Math.min(1, Math.max(0, v))
  }
  return (acc / pool.length) * 100
}

export function applyQuizAnswer(mastery, objectId, isCorrect) {
  const next = { ...(mastery || {}) }
  const cur = Math.max(0, Number(next[objectId] ?? 0))
  if (isCorrect) {
    next[objectId] = cur + CORRECT_DELTA
  } else {
    next[objectId] = Math.max(0, cur - WRONG_DELTA)
  }
  return next
}

export function pickNextQuestion(pool, mastery) {
  if (!Array.isArray(pool) || pool.length === 0) return null
  let minScore = Infinity
  const candidates = []
  for (const id of pool) {
    const score = Math.max(0, Number(mastery?.[id] ?? 0))
    if (score < minScore) {
      minScore = score
      candidates.length = 0
      candidates.push(id)
    } else if (score === minScore) {
      candidates.push(id)
    }
  }
  if (candidates.length === 0) return pool[Math.floor(Math.random() * pool.length)]
  return candidates[Math.floor(Math.random() * candidates.length)]
}
