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
    illumCos,
    isNearTerminator,
    realViewingConditions,
    randomViewingConditions,
    meanViewingConditions,
    LIMB_COS_CUTOFF,
    DIFFICULTY_MIN_SIZE_DEG,
  } from '../lib/moonMap.js'
  import {
    applyQuizAnswer,
    clearQuizState,
    computeProgressPct,
    loadQuizState,
    pickNextQuestion,
    saveQuizState,
  } from '../lib/quizFramework.js'

  export let time = new Date()

  const dispatch = createEventDispatcher()
  const QUIZ_TYPE = 'moon'
  const QUIZ_SETTINGS_KEY = 'observarium.moonQuiz.settings'
  const QUIZ_POOL_SIZE = 20
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
  let mastery = {}
  let currentQuestion = null
  let options = []
  let resolved = false
  let firstTapMade = false
  let wrongTapped = new Set()
  let feedback = ''
  let progressPct = 0

  // Fixed once per session when scope is 'local' (see IMPLEMENTATION_STEPS.md
  // Step 40 — "the real Moon doesn't move mid-session"), regardless of the
  // app's live clock ticking forward while the quiz is open.
  let sessionViewing = null

  let subLat = 0
  let subLon = 0
  let sunLon = null
  let moonCanvasRef

  $: allowLocal = difficulty !== 'easy'

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

  function isVisibleAtMeanView(feat) {
    const p = projectPoint(feat.lat, feat.lon, 0, 0)
    return p.cosC > LIMB_COS_CUTOFF
  }

  function buildPool(s, d) {
    const minSize = DIFFICULTY_MIN_SIZE_DEG[d] ?? DIFFICULTY_MIN_SIZE_DEG.medium
    const sizeEligible = allFeatures.filter((f) => f.sizeDeg >= minSize)

    if (d === 'easy' || s === 'global') {
      // Easy is always the fixed mean view; Global's per-question libration
      // stays close enough to the mean view (±~8°) that mean-view visibility
      // is the right eligibility test — actual per-question visibility is
      // guaranteed by the retry loop in loadQuestionView().
      return sizeEligible.filter(isVisibleAtMeanView).map((f) => f.id)
    }

    // Local: eligible only if actually lit and near the terminator under
    // this session's fixed real viewing conditions.
    const vc = sessionViewing
    return sizeEligible
      .filter((f) => {
        const p = projectPoint(f.lat, f.lon, vc.subLat, vc.subLon)
        if (p.cosC <= LIMB_COS_CUTOFF) return false
        return isNearTerminator(illumCos(f.lat, f.lon, vc.sunLon))
      })
      .map((f) => f.id)
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
    const distractors = pool.filter((id) => id !== correctId)
    for (let i = distractors.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[distractors[i], distractors[j]] = [distractors[j], distractors[i]]
    }
    const chosen = [correctId, ...distractors.slice(0, 3)]
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

    const freshPool = buildPool(scope, difficulty)
    if (freshPool.length < 4) {
      feedback =
        scope === 'local'
          ? 'Not enough features near the current terminator. Try Global scope or an easier level.'
          : 'Not enough features for this difficulty.'
      return
    }

    const saved = continuePrev ? loadQuizState(QUIZ_TYPE, difficulty, scope) : null
    if (saved?.pool?.length >= 4) {
      const validPool = saved.pool.filter((id) => freshPool.includes(id))
      pool = validPool.length >= 4 ? validPool : sampleIds(freshPool, QUIZ_POOL_SIZE)
      mastery = { ...(saved.mastery || {}) }
      currentQuestion = pool.includes(saved.currentQuestion) ? saved.currentQuestion : pickNextQuestion(pool, mastery)
    } else {
      pool = sampleIds(freshPool, QUIZ_POOL_SIZE)
      mastery = {}
      currentQuestion = pickNextQuestion(pool, mastery)
      clearQuizState(QUIZ_TYPE, difficulty, scope)
    }

    progressPct = computeProgressPct(pool, mastery)
    setupMode = false
    resolved = false
    firstTapMade = false
    wrongTapped = new Set()
    feedback = ''
    pickOptions(currentQuestion)
    loadQuestionView(currentQuestion)
    saveState()
  }

  function nextQuestion() {
    resolved = false
    firstTapMade = false
    wrongTapped = new Set()
    feedback = ''
    currentQuestion = pickNextQuestion(pool, mastery)
    if (!currentQuestion) return
    pickOptions(currentQuestion)
    loadQuestionView(currentQuestion)
    saveState()
  }

  function handleAnswer(optionId) {
    if (!currentQuestion) return
    if (resolved) {
      if (optionId === currentQuestion && progressPct < 100) nextQuestion()
      return
    }
    if (wrongTapped.has(optionId)) return
    const correct = optionId === currentQuestion
    if (!firstTapMade) {
      firstTapMade = true
      mastery = applyQuizAnswer(mastery, currentQuestion, correct)
      progressPct = computeProgressPct(pool, mastery)
      if (progressPct >= 100) clearQuizState(QUIZ_TYPE, difficulty, scope)
    }
    if (correct) {
      resolved = true
    } else {
      wrongTapped = new Set([...wrongTapped, optionId])
    }
    saveState()
  }

  function handleBack() {
    if (!setupMode) saveState()
    dispatch('close')
  }

  function onGlobalKeyDown(e) {
    if (setupMode || (resolved && progressPct >= 100) || options.length === 0) return
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

      <p class="question">
        {resolved && progressPct < 100
          ? 'Tap the highlighted answer again for the next question'
          : 'What is the name of the highlighted feature?'}
      </p>

      <div class="moon-wrap">
        <MoonCanvas
          bind:this={moonCanvasRef}
          features={allFeatures}
          {subLat}
          {subLon}
          {sunLon}
          highlightId={currentQuestion}
        />
        <button
          class="recenter-btn"
          type="button"
          on:click={() => moonCanvasRef?.centerOnHighlight()}
          title="Center on highlighted feature"
        >
          Center
        </button>
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

      {#if progressPct >= 100}
        <p class="done">Quiz complete. 100% mastery reached.</p>
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

  .recenter-btn {
    position: absolute;
    right: 0.5rem;
    bottom: 0.5rem;
    border: 1px solid rgba(180, 0, 0, 0.5);
    background: rgba(0, 0, 0, 0.7);
    color: var(--fg);
    border-radius: 6px;
    padding: 0.3rem 0.55rem;
    font-size: 0.8rem;
    cursor: pointer;
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
