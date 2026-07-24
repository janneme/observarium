<script>
  import { createEventDispatcher, onDestroy, onMount } from 'svelte'
  import { theme } from '../stores/theme.js'
  import SkyCanvas from '../components/SkyCanvas.svelte'
  import QuizSetup from '../components/QuizSetup.svelte'
  import QuizProgress from '../components/QuizProgress.svelte'
  import TickIcon from '../icons/TickIcon.svelte'
  import CloseIcon from '../icons/CloseIcon.svelte'
  import ThumbUpIcon from '../icons/ThumbUpIcon.svelte'
  import ThumbDownIcon from '../icons/ThumbDownIcon.svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import { getObjectsInArea, getObjectImage, getSearchIndex } from '../lib/db.js'
  import { firstDisplayName, preferredCatalogLabel } from '../lib/search.js'
  import {
    buildEligiblePool,
    pickPositionDistractors,
    pickImageDistractors,
    pickNameDistractors,
    QUESTION_COUNTS,
  } from '../lib/deepSkyQuizPool.js'
  import {
    applyQuizAnswer,
    clearQuizState,
    computeProgressPct,
    loadQuizState,
    pickNextQuestion,
    saveQuizState,
  } from '../lib/quizFramework.js'

  export let lat = 48.2
  export let lon = 16.37
  export let time = new Date()
  export let viewRa0 = 0
  export let viewDec0 = 0
  export let viewFov = 60

  const dispatch = createEventDispatcher()
  const QUIZ_TYPE = 'deepsky'
  const QUIZ_SETTINGS_KEY = 'observarium.deepSkyQuiz.settings'
  // Fixed across all difficulties (unlike Star/Constellation Quiz) — see deep_sky_quiz.md.
  const DEEP_SKY_QUIZ_FOV_DEG = 40
  // Below this angular separation from the target, a candidate distractor is
  // too easily confused with it in the rendered FOV (e.g. M81/M82, ~0.6deg
  // apart) to be a fair "position" question distractor.
  const MIN_POSITION_SEP_DEG = DEEP_SKY_QUIZ_FOV_DEG * 0.15
  // The catalogue only covers dec >= -35° (Europe visibility filter). A
  // "position" question centred on an object too close to that edge would
  // render with its neighbourhood cut off.
  const EUROPE_MIN_DEC = -35
  const QUERY_MAG = 6
  // Below this many image-eligible pool candidates, 'image' questions aren't offered this session.
  const IMAGE_MIN_POOL = 4

  let loading = true
  let setupMode = true
  let allDsos = []
  let dsosById = new Map()
  let dsoImageIds = new Set()

  let scope = 'global'
  let difficulty = 'medium'
  let hasSaved = false
  let settingsLoaded = false

  let pool = [] // composite ids: `${objectId}::${questionType}`
  let mastery = {}
  let currentQuestion = null
  let currentObjId = null
  let currentType = null
  let nameDirection = 'askName' // 'askName' | 'askCat'
  let options = [] // array of object ids
  let revealLines = false
  let resolved = false
  let firstTapMade = false
  let wrongTapped = new Set()
  let feedback = ''
  let progressPct = 0

  let qRa0 = 0
  let qDec0 = 0
  let qObjects = []
  let imageUrls = new Map() // objectId -> blob URL, for the current question's tiles

  function parseComposite(compositeId) {
    const idx = compositeId.lastIndexOf('::')
    return { objId: compositeId.slice(0, idx), qType: compositeId.slice(idx + 2) }
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

  function angSepDeg([ra1, dec1], [ra2, dec2]) {
    const r = Math.PI / 180
    return (
      Math.acos(
        Math.max(
          -1,
          Math.min(
            1,
            Math.sin(dec1 * r) * Math.sin(dec2 * r) +
              Math.cos(dec1 * r) * Math.cos(dec2 * r) * Math.cos((ra2 - ra1) * r),
          ),
        ),
      ) / r
    )
  }

  function computeLocalRadiusDeg() {
    return Math.max(25, (Number(viewFov) || 60) * 1.4)
  }

  function hasImage(id) {
    return dsoImageIds.has(id)
  }

  function canBePosition(dso) {
    return Number.isFinite(dso.pos?.[1]) && dso.pos[1] >= EUROPE_MIN_DEC + DEEP_SKY_QUIZ_FOV_DEG / 2
  }

  function buildBasePool(s, d) {
    const scoped =
      s === 'local'
        ? allDsos.filter((dso) => angSepDeg(dso.pos, [viewRa0, viewDec0]) <= computeLocalRadiusDeg())
        : allDsos
    return buildEligiblePool(scoped, d, hasImage)
  }

  function sampleIds(ids, n) {
    const arr = [...ids]
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[arr[i], arr[j]] = [arr[j], arr[i]]
    }
    return arr.slice(0, n)
  }

  // Assigns a fixed question type to each sampled object id, per
  // deep_sky_quiz.md's "Question Set Generation": the quizzed object AND
  // question type are both fixed once the question set is generated.
  // 'name' is only offered for objects that actually have a real name —
  // otherwise "What is the catalogue number of <its own catalogue number>?"
  // would be a nonsense, self-referential question.
  function assignTypes(objIds, imageEligible) {
    return objIds.map((id) => {
      const dso = dsosById.get(id)
      const types = []
      if (canBePosition(dso)) types.push('position')
      if (hasRealName(id)) types.push('name')
      if (imageEligible && hasImage(id)) types.push('image')
      if (types.length === 0) types.push('position')
      const t = types[Math.floor(Math.random() * types.length)]
      return `${id}::${t}`
    })
  }

  function catalogLabel(dso) {
    return preferredCatalogLabel(dso) || dso?.id || '?'
  }

  function displayName(dso) {
    return firstDisplayName(dso?.name) || catalogLabel(dso)
  }

  function hasRealName(objId) {
    return !!firstDisplayName(dsosById.get(objId)?.name)
  }

  function optionLabel(objId) {
    const dso = dsosById.get(objId)
    if (currentType === 'position') return catalogLabel(dso)
    if (currentType === 'name') return nameDirection === 'askName' ? displayName(dso) : catalogLabel(dso)
    return catalogLabel(dso)
  }

  function baseObjIds() {
    return [...new Set(pool.map((c) => parseComposite(c).objId))]
  }

  function revokeImageUrls() {
    for (const url of imageUrls.values()) URL.revokeObjectURL(url)
    imageUrls = new Map()
  }

  async function loadImageTiles(objIds) {
    revokeImageUrls()
    const next = new Map()
    await Promise.all(
      objIds.map(async (id) => {
        const rec = await getObjectImage(id)
        if (rec?.blob) next.set(id, URL.createObjectURL(rec.blob))
      }),
    )
    imageUrls = next
  }

  async function loadQuestionContent(objId, qType) {
    const target = dsosById.get(objId)
    const base = baseObjIds()

    if (qType === 'position') {
      qRa0 = target.pos[0]
      qDec0 = target.pos[1]
      revealLines = difficulty !== 'hard'
      const margin = Math.max(DEEP_SKY_QUIZ_FOV_DEG * 0.6, 15)
      qObjects = await getObjectsInArea(qRa0 - margin, qRa0 + margin, qDec0 - margin, qDec0 + margin, QUERY_MAG)
      const distractors = pickPositionDistractors(objId, base, dsosById, MIN_POSITION_SEP_DEG, 3)
      options = [objId, ...distractors].sort(() => Math.random() - 0.5)
    } else if (qType === 'image') {
      let distractors = pickImageDistractors(objId, base, dsosById, dsoImageIds, 3)
      if (distractors.length < 3) {
        const padding = [...dsoImageIds].filter((id) => id !== objId && !distractors.includes(id) && dsosById.has(id))
        distractors = [...distractors, ...sampleIds(padding, 3 - distractors.length)]
      }
      options = [objId, ...distractors].sort(() => Math.random() - 0.5)
      await loadImageTiles(options)
    } else {
      // 'name' type is only ever assigned to objects with a real name (see
      // assignTypes), so the target always has one here. "askName" options
      // must all be real names too — otherwise a distractor falling back to
      // its own catalogue number would be trivially distinguishable from the
      // correct (real) name — so fall back to "askCat" if too few exist.
      const namedPool = base.filter(hasRealName)
      nameDirection = namedPool.length >= 4 && Math.random() < 0.5 ? 'askName' : 'askCat'
      const candidatePool = nameDirection === 'askName' ? namedPool : base
      const distractors = pickNameDistractors(objId, candidatePool, 3)
      options = [objId, ...distractors].sort(() => Math.random() - 0.5)
    }
  }

  function saveState() {
    saveQuizState(QUIZ_TYPE, difficulty, scope, { pool, mastery, currentQuestion })
  }

  async function loadQuestion(compositeId) {
    const { objId, qType } = parseComposite(compositeId)
    currentObjId = objId
    currentType = qType
    resolved = false
    firstTapMade = false
    wrongTapped = new Set()
    feedback = ''
    await loadQuestionContent(objId, qType)
  }

  async function beginQuiz(continuePrev) {
    const baseIds = buildBasePool(scope, difficulty)
    if (baseIds.length < 4) {
      feedback = 'Not enough deep sky objects for this scope/difficulty. Try Global or an easier level.'
      return
    }
    const imageEligibleCount = baseIds.filter(hasImage).length
    const imageEligible = imageEligibleCount >= IMAGE_MIN_POOL

    const saved = continuePrev ? loadQuizState(QUIZ_TYPE, difficulty, scope) : null
    if (saved?.pool?.length >= 4) {
      const baseSet = new Set(baseIds)
      const validPool = saved.pool.filter((c) => {
        const { objId, qType } = parseComposite(c)
        if (!baseSet.has(objId)) return false
        if (qType === 'image' && !hasImage(objId)) return false
        if (qType === 'position' && !canBePosition(dsosById.get(objId))) return false
        if (qType === 'name' && !hasRealName(objId)) return false
        return true
      })
      pool =
        validPool.length >= 4 ? validPool : assignTypes(sampleIds(baseIds, QUESTION_COUNTS[difficulty]), imageEligible)
      mastery = { ...(saved.mastery || {}) }
      currentQuestion = pool.includes(saved.currentQuestion) ? saved.currentQuestion : pickNextQuestion(pool, mastery)
    } else {
      const sampled = sampleIds(baseIds, QUESTION_COUNTS[difficulty])
      pool = assignTypes(sampled, imageEligible)
      mastery = {}
      currentQuestion = pickNextQuestion(pool, mastery)
      clearQuizState(QUIZ_TYPE, difficulty, scope)
    }

    progressPct = computeProgressPct(pool, mastery)
    setupMode = false
    await loadQuestion(currentQuestion)
    saveState()
  }

  async function nextQuestion() {
    currentQuestion = pickNextQuestion(pool, mastery)
    if (!currentQuestion) return
    await loadQuestion(currentQuestion)
    saveState()
  }

  function scoreAnswer(correct) {
    if (!firstTapMade) {
      firstTapMade = true
      mastery = applyQuizAnswer(mastery, currentQuestion, correct)
      progressPct = computeProgressPct(pool, mastery)
      if (progressPct >= 100) clearQuizState(QUIZ_TYPE, difficulty, scope)
    }
  }

  async function handleAnswer(optionId) {
    if (!currentQuestion) return
    if (resolved) {
      if (optionId === currentObjId && progressPct < 100) await nextQuestion()
      return
    }
    if (wrongTapped.has(optionId)) return
    if (currentType === 'position') revealLines = true
    const correct = optionId === currentObjId
    scoreAnswer(correct)
    if (correct) {
      resolved = true
    } else {
      wrongTapped = new Set([...wrongTapped, optionId])
    }
    saveState()
  }

  function handleAdvanceTap() {
    if (resolved && progressPct < 100) nextQuestion()
  }

  function handleBack() {
    if (!setupMode) saveState()
    revokeImageUrls()
    dispatch('close')
  }

  function onGlobalKeyDown(e) {
    if (setupMode || currentType === 'image' || (resolved && progressPct >= 100) || options.length === 0) return
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
      const index = await getSearchIndex()
      allDsos = index.filter((x) => x.type === 'dso' && Array.isArray(x.pos))
      dsosById = new Map(allDsos.map((d) => [d.id, d]))
      const imageChecks = await Promise.all(
        allDsos.map(async (d) => ((await getObjectImage(d.id))?.blob ? d.id : null)),
      )
      dsoImageIds = new Set(imageChecks.filter(Boolean))
      loading = false
    })()
  })

  onDestroy(() => {
    window.removeEventListener('keydown', onGlobalKeyDown, true)
    revokeImageUrls()
  })
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={handleBack} aria-label="Back">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="title">Deep Sky Quiz</span>
  </div>

  <div class="body">
    {#if loading}
      <p class="msg">Loading deep sky object index...</p>
    {:else if setupMode}
      <QuizSetup
        title="Deep Sky Quiz"
        {hasSaved}
        initialDifficulty={difficulty}
        initialScope={scope}
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
      {#if feedback}
        <p class="msg error">{feedback}</p>
      {/if}
    {:else}
      {@const target = dsosById.get(currentObjId)}
      <QuizProgress {progressPct} />

      {#if currentType !== 'name'}
        <p class="question">
          {#if resolved && progressPct < 100}
            {currentType === 'image' ? 'Tap the image again to continue' : 'Tap here for the next question'}
          {:else if currentType === 'position'}
            What object can you find here?
          {:else}
            Which object is {catalogLabel(target)}?
          {/if}
        </p>
      {/if}

      {#if currentType === 'position'}
        <div
          class="sky-wrap"
          class:tappable={resolved && progressPct < 100}
          role="button"
          tabindex="0"
          on:click={handleAdvanceTap}
          on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && handleAdvanceTap()}
        >
          <SkyCanvas
            ra0={qRa0}
            dec0={qDec0}
            fov={DEEP_SKY_QUIZ_FOV_DEG}
            objects={qObjects}
            targetMarker={Array.isArray(target?.pos) ? target.pos : null}
            targetMarkerColor="rgba(120,0,255,0.9)"
            constellationLineColorOverride={revealLines && $theme !== 'nightly' ? 'rgba(255,0,255,0.85)' : null}
            {lat}
            {lon}
            {time}
            finderMode={false}
            showFovCircle={false}
            showConstellationLines={revealLines}
            showConstellationNames={false}
            showConstellationBoundaries={false}
            showDsos={false}
            showSpecialStarSymbols={false}
            showHorizon={false}
            showSolarSystem={false}
          />
        </div>

        <div class="answers">
          {#each options as oid}
            {@const isCorrect = oid === currentObjId}
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
              <span class="answer-label">{optionLabel(oid)}</span>
              {#if resolved && isCorrect}
                <ThumbUpIcon size="1.1rem" aria-hidden="true" />
              {:else if isWrongTapped}
                <ThumbDownIcon size="1.1rem" aria-hidden="true" />
              {/if}
            </button>
          {/each}
        </div>
      {:else if currentType === 'image'}
        <div class="image-grid">
          {#each options as oid}
            {@const isCorrect = oid === currentObjId}
            {@const isWrongTapped = wrongTapped.has(oid)}
            {@const isSkipped = resolved && !isCorrect && !isWrongTapped}
            <button
              class="image-tile"
              class:wrong={isWrongTapped}
              class:skipped={isSkipped}
              disabled={isWrongTapped || isSkipped || (resolved && !isCorrect)}
              on:click={() => handleAnswer(oid)}
            >
              {#if imageUrls.get(oid)}
                <img src={imageUrls.get(oid)} alt="" />
              {/if}
              {#if resolved && isCorrect}
                <span class="tile-overlay correct"><TickIcon size="2rem" aria-hidden="true" /></span>
              {:else if isWrongTapped}
                <span class="tile-overlay wrong"><CloseIcon size="2rem" aria-hidden="true" /></span>
              {/if}
            </button>
          {/each}
        </div>
      {:else}
        <div
          class="name-box"
          class:tappable={resolved && progressPct < 100}
          role="button"
          tabindex="0"
          on:click={handleAdvanceTap}
          on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && handleAdvanceTap()}
        >
          <p class="name-question">
            {#if resolved && progressPct < 100}
              Tap here for the next question
            {:else if nameDirection === 'askName'}
              What is the name of {catalogLabel(target)}?
            {:else}
              What is the catalogue number of {displayName(target)}?
            {/if}
          </p>
        </div>

        <div class="answers">
          {#each options as oid}
            {@const isCorrect = oid === currentObjId}
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
              <span class="answer-label">{optionLabel(oid)}</span>
              {#if resolved && isCorrect}
                <ThumbUpIcon size="1.1rem" aria-hidden="true" />
              {:else if isWrongTapped}
                <ThumbDownIcon size="1.1rem" aria-hidden="true" />
              {/if}
            </button>
          {/each}
        </div>
      {/if}

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

  .sky-wrap,
  .name-box,
  .image-grid {
    position: relative;
    width: 100%;
    max-width: 520px;
    aspect-ratio: 1 / 1;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid rgba(180, 0, 0, 0.45);
    align-self: center;
  }

  .name-box {
    background: rgba(0, 0, 0, 0.35);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.4rem;
  }

  .name-question {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 700;
    text-align: center;
    line-height: 1.35;
  }

  .sky-wrap.tappable,
  .name-box.tappable {
    cursor: pointer;
  }

  .image-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: 1fr 1fr;
    gap: 2px;
    background: rgba(180, 0, 0, 0.45);
  }

  .image-tile {
    position: relative;
    padding: 0;
    margin: 0;
    border: none;
    background: rgba(0, 0, 0, 0.7);
    cursor: pointer;
    overflow: hidden;
  }

  .image-tile:disabled {
    cursor: default;
  }

  .image-tile img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .image-tile.wrong img,
  .image-tile.skipped img {
    filter: brightness(0.35);
  }

  .tile-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
  }

  .tile-overlay.correct {
    color: rgba(140, 160, 255, 1);
  }

  :global([data-theme='nightly']) .tile-overlay.correct {
    color: #ff0044;
  }

  .tile-overlay.wrong {
    color: rgba(255, 90, 90, 1);
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
