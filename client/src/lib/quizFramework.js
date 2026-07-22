// Per-question progress model: mastery[id] = { chain, everWrong }.
//   chain      = consecutive first-attempt-correct answers since the last
//                incorrect first attempt (or since the quiz began).
//   everWrong  = whether this question has ever been answered incorrectly
//                on the first attempt; once true, needs `chain >= 3` to pass
//                (a single lucky guess shouldn't pass a question the user
//                doesn't actually know). A never-wrong question needs
//                `chain >= 2` (two correct attempts in a row).
function required(state) {
  return state.everWrong ? 3 : 2
}

function questionScore(state) {
  const req = required(state)
  if (state.chain >= req) return 1
  return state.chain / req
}

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

function stateOf(mastery, id) {
  return mastery?.[id] || { chain: 0, everWrong: false }
}

// A wrong first attempt lowers progress by growing the denominator
// (required jumps to 3) without adding to the numerator, so it visibly dips
// the progress bar even though no correct answer was undone.
export function computeProgressPct(pool, mastery) {
  if (!Array.isArray(pool) || pool.length === 0) return 0
  let achieved = 0
  let totalReq = 0
  for (const id of pool) {
    const s = stateOf(mastery, id)
    const req = required(s)
    totalReq += req
    achieved += Math.min(s.chain, req)
  }
  return totalReq > 0 ? (achieved / totalReq) * 100 : 0
}

export function applyQuizAnswer(mastery, objectId, isCorrect) {
  const next = { ...(mastery || {}) }
  const prev = stateOf(next, objectId)
  next[objectId] = isCorrect ? { chain: prev.chain + 1, everWrong: prev.everWrong } : { chain: 0, everWrong: true }
  return next
}

export function pickNextQuestion(pool, mastery) {
  if (!Array.isArray(pool) || pool.length === 0) return null
  let minScore = Infinity
  const candidates = []
  for (const id of pool) {
    const score = questionScore(stateOf(mastery, id))
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
