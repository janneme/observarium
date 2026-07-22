<script>
  import { createEventDispatcher, onMount } from 'svelte'
  import QuizSetup from '../components/QuizSetup.svelte'
  import QuizProgress from '../components/QuizProgress.svelte'
  import MoonCanvas from '../components/MoonCanvas.svelte'
  import ThumbUpIcon from '../icons/ThumbUpIcon.svelte'
  import ThumbDownIcon from '../icons/ThumbDownIcon.svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import { getMeta } from '../lib/db.js'
  import {
    flattenMoonFeatures,
    projectPoint,
    realViewingConditions,
    randomViewingConditions,
    meanViewingConditions,
    LIMB_COS_CUTOFF,
  } from '../lib/moonMap.js'
  import { buildGlobalPools, buildLocalPools, pickDistractors } from '../lib/moonQuizPools.js'
  import { clearQuizState, loadQuizState, saveQuizState } from '../lib/quizFramework.js'

  export let time = new Date()

  const dispatch = createEventDispatcher()
  const QUIZ_TYPE = 'moon'
  const QUIZ_SETTINGS_KEY = 'observarium.moonQuiz.settings'
  // Question-set size per difficulty (like the Constellation Quiz's
  // QUIZ_QUESTION_COUNT, but tiered — Easy/Medium's pools are themselves
  // smaller than Hard's, see moonQuizPools.js).
  const QUIZ_QUESTION_COUNTS = { easy: 15, medium: 30, hard: 50 }
  // How many attempts to re-roll a random (Global scope) libration before
  // giving up and falling back to the mean view — libration's range is
  // small (~±8°), so a size-eligible feature almost always stays visible.
  const GLOBAL_VIEW_RETRIES = 20

  let loading = true
  let setupMode = true
  let allFeatures = []
  let featuresById = new Map()

  let scope = 'global'
  let difficulty = 'medium'
  let hasSaved = false
  let settingsLoaded = false

  let pool = []
  // What MoonCanvas renders — always the Hard-tier pool for the current
  // scope, independent of `difficulty` (see IMPLEMENTATION_STEPS.md Step 40
  // "Rendered map contents"). Not persisted; cheap to recompute per session.
  let renderPool = []
  // Per-question progress, adapted from the Constellation Quiz's model (Step
  // 37b) — chain/everWrong tracking is the same, but the pass thresholds are
  // higher: a single lucky correct guess shouldn't pass a question the user
  // doesn't actually know. mastery[id] = { chain, everWrong }.
  //   chain      = consecutive first-attempt-correct answers since the last
  //                incorrect first attempt (or since the quiz began).
  //   everWrong  = whether this question has ever been answered incorrectly
  //                on the first attempt; once true, needs `chain >= 3` to pass.
  // A never-wrong question needs `chain >= 2` (two correct attempts in a
  // row) to pass.
  let mastery = {}
  let currentQuestion = null
  let options = []
  let resolved = false
  let firstTapMade = false
  let wrongTapped = new Set()
  let feedback = ''

  // Fixed once per session when scope is 'local' (see IMPLEMENTATION_STEPS.md
  // Step 40 — "the real Moon doesn't move mid-session"), regardless of the
  // app's live clock ticking forward while the quiz is open.
  let sessionViewing = null

  let subLat = 0
  let subLon = 0
  let sunLon = null

  $: allowLocal = difficulty !== 'easy'
  $: renderFeatures = renderPool.map((id) => featuresById.get(id)).filter(Boolean)

  function questionState(id) {
    return mastery[id] || { chain: 0, everWrong: false }
  }
  function required(state) {
    return state.everWrong ? 3 : 2
  }
  function questionScore(state) {
    const req = required(state)
    if (state.chain >= req) return 1
    return state.chain / req
  }
  function isPassed(id) {
    return questionScore(questionState(id)) >= 1
  }
  function applyAttempt(m, id, correct) {
    const prev = m[id] || { chain: 0, everWrong: false }
    if (correct) return { ...m, [id]: { chain: prev.chain + 1, everWrong: prev.everWrong } }
    return { ...m, [id]: { chain: 0, everWrong: true } }
  }

  // Adapted from ConstellationIdQuizScreen.svelte's formula: a wrong first
  // attempt lowers progress by growing the denominator (required jumps to 3)
  // without adding to the numerator, so it visibly dips the progress bar.
  $: progressPct = ((m, p) => {
    if (!p.length) return 0
    let achieved = 0
    let totalReq = 0
    for (const id of p) {
      const s = m[id] || { chain: 0, everWrong: false }
      const req = s.everWrong ? 3 : 2
      totalReq += req
      achieved += Math.min(s.chain, req)
    }
    return totalReq > 0 ? (achieved / totalReq) * 100 : 0
  })(mastery, pool)
  $: allPassed = pool.length > 0 && pool.every((id) => isPassed(id))

  // Pick the next unpassed question, preferring the lowest score (so
  // partly-progressed retries don't dominate), random tie-break, avoiding
  // the just-answered question when other unpassed ones exist.
  function pickNextUnpassed(excludeId) {
    const unpassed = pool.filter((id) => !isPassed(id))
    if (unpassed.length === 0) return null
    const others = unpassed.filter((id) => id !== excludeId)
    const searchIn = others.length > 0 ? others : unpassed
    const scored = searchIn.map((id) => ({ id, score: questionScore(questionState(id)) }))
    const minScore = Math.min(...scored.map((s) => s.score))
    const candidates = scored.filter((s) => s.score === minScore).map((s) => s.id)
    return candidates[Math.floor(Math.random() * candidates.length)]
  }

  function updateHasSaved() {
    hasSaved = !!loadQuizState(QUIZ_TYPE, difficulty, scope)
  }

  function loadQuizSettings() {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage?.getItem(QUIZ_SETTINGS_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw)
      const s = String(parsed?.scope || '')
      const d = String(parsed?.difficulty || '')
      if (s === 'global' || s === 'local') scope = s
      if (d === 'easy' || d === 'medium' || d === 'hard') difficulty = d
      if (difficulty === 'easy') scope = 'global'
    } catch {
      return
    }
  }

  function saveQuizSettings(nextScope, nextDifficulty) {
    if (typeof window === 'undefined') return
    try {
      window.localStorage?.setItem(QUIZ_SETTINGS_KEY, JSON.stringify({ scope: nextScope, difficulty: nextDifficulty }))
    } catch {
      return
    }
  }

  function buildPools(s, d) {
    // Easy is always the fixed mean view/Global-only pool, regardless of the
    // selected scope (Local is hidden in QuizSetup at this difficulty).
    if (d === 'easy' || s === 'global') return buildGlobalPools(allFeatures, d)
    return buildLocalPools(allFeatures, d, sessionViewing)
  }

  function loadQuestionView(targetId) {
    const feat = featuresById.get(targetId)
    if (difficulty === 'easy') {
      const vc = meanViewingConditions()
      subLat = vc.subLat
      subLon = vc.subLon
      sunLon = vc.sunLon
      return
    }
    if (scope === 'local') {
      subLat = sessionViewing.subLat
      subLon = sessionViewing.subLon
      sunLon = sessionViewing.sunLon
      return
    }
    let vc = randomViewingConditions()
    for (let i = 0; i < GLOBAL_VIEW_RETRIES; i++) {
      const p = projectPoint(feat.lat, feat.lon, vc.subLat, vc.subLon)
      if (p.cosC > LIMB_COS_CUTOFF) break
      vc = randomViewingConditions()
    }
    subLat = vc.subLat
    subLon = vc.subLon
    sunLon = vc.sunLon
  }

  function sampleIds(ids, n) {
    const arr = [...ids]
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[arr[i], arr[j]] = [arr[j], arr[i]]
    }
    return arr.slice(0, n)
  }

  function pickOptions(correctId) {
    const target = featuresById.get(correctId)
    const distractors = pickDistractors(target, pool, renderPool, featuresById, 3)
    const chosen = [correctId, ...distractors]
    for (let i = chosen.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[chosen[i], chosen[j]] = [chosen[j], chosen[i]]
    }
    options = chosen
  }

  function saveState() {
    saveQuizState(QUIZ_TYPE, difficulty, scope, { pool, mastery, currentQuestion })
  }

  async function beginQuiz(continuePrev) {
    if (scope === 'local') {
      sessionViewing = realViewingConditions(time)
    } else {
      sessionViewing = null
    }

    const { questionPool: freshPool, renderPool: freshRenderPool } = buildPools(scope, difficulty)
    if (freshPool.length < 4) {
      feedback =
        scope === 'local'
          ? 'Not enough features near the current terminator. Try Global scope or an easier level.'
          : 'Not enough features for this difficulty.'
      return
    }
    renderPool = freshRenderPool

    const questionCount = QUIZ_QUESTION_COUNTS[difficulty] ?? 30
    const saved = continuePrev ? loadQuizState(QUIZ_TYPE, difficulty, scope) : null
    if (saved?.pool?.length >= 4) {
      const validPool = saved.pool.filter((id) => freshPool.includes(id))
      pool = validPool.length >= 4 ? validPool : sampleIds(freshPool, questionCount)
      mastery = { ...(saved.mastery || {}) }
      currentQuestion = pool.includes(saved.currentQuestion) ? saved.currentQuestion : pickNextUnpassed(null)
    } else {
      pool = sampleIds(freshPool, questionCount)
      mastery = {}
      currentQuestion = pool[0]
      clearQuizState(QUIZ_TYPE, difficulty, scope)
    }

    setupMode = false
    resolved = false
    firstTapMade = false
    wrongTapped = new Set()
    feedback = ''
    if (currentQuestion) {
      pickOptions(currentQuestion)
      loadQuestionView(currentQuestion)
    }
    saveState()
  }

  function nextQuestion() {
    const next = pickNextUnpassed(currentQuestion)
    if (!next) {
      currentQuestion = null
      clearQuizState(QUIZ_TYPE, difficulty, scope)
      return
    }
    currentQuestion = next
    resolved = false
    firstTapMade = false
    wrongTapped = new Set()
    feedback = ''
    pickOptions(currentQuestion)
    loadQuestionView(currentQuestion)
    saveState()
  }

  function handleAnswer(optionId) {
    if (!currentQuestion) return
    if (resolved) {
      if (optionId === currentQuestion && !allPassed) nextQuestion()
      return
    }
    if (wrongTapped.has(optionId)) return
    const correct = optionId === currentQuestion
    if (!firstTapMade) {
      firstTapMade = true
      mastery = applyAttempt(mastery, currentQuestion, correct)
    }
    if (correct) {
      resolved = true
    } else {
      wrongTapped = new Set([...wrongTapped, optionId])
    }
    saveState()
  }

  function handleBack() {
    if (!setupMode && currentQuestion) saveState()
    dispatch('close')
  }

  function onGlobalKeyDown(e) {
    if (setupMode || !currentQuestion || options.length === 0) return
    if (e.defaultPrevented || e.repeat || e.metaKey || e.ctrlKey || e.altKey) return
    const t = e.target
    const tag = String(t?.tagName || '').toLowerCase()
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || t?.isContentEditable) return
    const key = String(e.key || '').toLowerCase()
    const idx = key === 'a' ? 0 : key === 'b' ? 1 : key === 'c' ? 2 : key === 'd' ? 3 : -1
    if (idx < 0 || idx >= options.length) return
    e.preventDefault()
    handleAnswer(options[idx])
  }

  $: if (setupMode) updateHasSaved()
  $: if (setupMode && settingsLoaded) saveQuizSettings(scope, difficulty)

  onMount(() => {
    window.addEventListener('keydown', onGlobalKeyDown, true)
    ;(async () => {
      loadQuizSettings()
      settingsLoaded = true
      const raw = await getMeta('moon_features')
      allFeatures = flattenMoonFeatures(raw)
      featuresById = new Map(allFeatures.map((f) => [f.id, f]))
      loading = false
    })()
    return () => window.removeEventListener('keydown', onGlobalKeyDown, true)
  })
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={handleBack} aria-label="Back">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="title">Moon Quiz</span>
  </div>

  <div class="body">
    {#if loading}
      <p class="msg">Loading Moon feature data...</p>
    {:else if setupMode}
      <QuizSetup
        title="Moon Quiz"
        {hasSaved}
        initialDifficulty={difficulty}
        initialScope={scope}
        {allowLocal}
        on:change={(e) => {
          difficulty = e.detail.difficulty
          scope = e.detail.scope
          updateHasSaved()
        }}
        on:start={async (e) => {
          difficulty = e.detail.difficulty
          scope = e.detail.scope
          await beginQuiz(e.detail.continuePrev)
        }}
      />
      <p class="hint">
        Easy always shows the full Moon disc — big, prominent features only. From Medium up, choose Global (full disc,
        viewing angle varies each question) or Local (restricted to features near tonight's actual terminator).
      </p>
      {#if feedback}
        <p class="msg error">{feedback}</p>
      {/if}
    {:else}
      <QuizProgress {progressPct} />

      {#if allPassed || !currentQuestion}
        <p class="done">Quiz complete. Every question passed.</p>
      {:else}
        <p class="question">
          {resolved ? 'Tap the highlighted answer again for the next question' : 'What is the name of the highlighted feature?'}
        </p>

        <div class="moon-wrap">
          <MoonCanvas
            features={renderFeatures}
            fixedFeatureSet={true}
            forceScale={difficulty === 'easy' ? 1 : null}
            {subLat}
            {subLon}
            {sunLon}
            highlightId={currentQuestion}
          />
        </div>

        <div class="answers">
          {#each options as oid}
            {@const feat = featuresById.get(oid)}
            {@const isCorrect = oid === currentQuestion}
            {@const isWrongTapped = wrongTapped.has(oid)}
            {@const isSkipped = resolved && !isCorrect && !isWrongTapped}
            <button
              class="answer"
              class:correct={resolved && isCorrect}
              class:wrong={isWrongTapped}
              class:skipped={isSkipped}
              disabled={isWrongTapped || isSkipped}
              on:click={() => handleAnswer(oid)}
            >
              <span class="answer-label">{feat?.name || 'Unknown'}</span>
              {#if resolved && isCorrect}
                <ThumbUpIcon size="1.1rem" aria-hidden="true" />
              {:else if isWrongTapped}
                <ThumbDownIcon size="1.1rem" aria-hidden="true" />
              {/if}
            </button>
          {/each}
        </div>
      {/if}
    {/if}
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    top: 2.75rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 22;
    background: var(--bg);
    color: var(--fg);
    display: flex;
    flex-direction: column;
  }

  .header {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.5rem 0.65rem;
    border-bottom: 1px solid rgba(180, 0, 0, 0.35);
  }

  .back-btn {
    background: none;
    border: none;
    color: var(--fg);
    cursor: pointer;
    padding: 0.25rem 0.15rem 0.25rem 0.5rem;
    border-radius: 4px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .back-btn:hover {
    background: rgba(200, 0, 0, 0.1);
  }

  .title {
    font-weight: 700;
  }

  .body {
    padding: 0.7rem;
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
    flex: 1;
    min-height: 0;
  }

  .question {
    margin: 0;
    font-size: 0.95rem;
  }

  .hint {
    margin: 0.4rem 0 0;
    font-size: 0.82rem;
    opacity: 0.75;
    max-width: 520px;
  }

  .moon-wrap {
    position: relative;
    width: 100%;
    max-width: 520px;
    aspect-ratio: 1 / 1;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid rgba(180, 0, 0, 0.45);
    align-self: center;
  }

  .answers {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.45rem;
    width: 100%;
    max-width: 520px;
    align-self: center;
  }

  .answer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    text-align: left;
    border: 1px solid rgba(180, 0, 0, 0.4);
    border-radius: 8px;
    background: rgba(0, 0, 0, 0.7);
    color: var(--fg);
    padding: 0.48rem 0.56rem;
    font-size: 1.2rem;
    cursor: pointer;
  }

  .answer:disabled {
    cursor: default;
  }

  .answer-label {
    min-width: 0;
  }

  .answer.correct {
    border-color: rgba(0, 0, 220, 0.9);
    background: rgba(0, 0, 200, 0.18);
    color: rgba(170, 190, 255, 1);
  }

  :global([data-theme='nightly']) .answer.correct {
    border-color: #ff0044;
    background: rgba(255, 0, 68, 0.18);
    color: #ff0044;
  }

  .answer.wrong .answer-label {
    text-decoration: line-through;
    opacity: 0.7;
  }

  .answer.skipped .answer-label {
    text-decoration: line-through;
    opacity: 0.55;
  }

  .msg {
    margin: 0;
    font-size: 0.86rem;
    color: var(--fg);
  }

  .msg.error {
    color: rgba(200, 0, 0, 0.9);
  }

  .done {
    margin: 0.5rem 0;
    color: rgba(0, 0, 200, 0.9);
    font-size: 0.95rem;
  }
</style>
