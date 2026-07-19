<script>
  import { createEventDispatcher, onDestroy, onMount } from 'svelte'
  import { theme } from '../stores/theme.js'
  import SkyCanvas from '../components/SkyCanvas.svelte'
  import QuizSetup from '../components/QuizSetup.svelte'
  import QuizProgress from '../components/QuizProgress.svelte'
  import ThumbUpIcon from '../icons/ThumbUpIcon.svelte'
  import ThumbDownIcon from '../icons/ThumbDownIcon.svelte'
  import BackIcon from '../icons/BackIcon.svelte'
  import { getMeta, getObjectsInArea, getSearchIndex } from '../lib/db.js'
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
  const QUIZ_TYPE = 'constellation'
  const DIFFICULTY_MAX_MAG = { easy: 1.5, medium: 2.5, hard: 4 }
  const QUIZ_SETTINGS_KEY = 'observarium.constellationQuiz.settings'
  // Cap the quiz to a fixed-size random sample so it has a definite end,
  // rather than cycling through every eligible star indefinitely.
  const QUIZ_POOL_SIZE = 20
  // The star catalogue only covers dec >= -35° (Europe visibility filter, see
  // data_prep/config.py). A quiz star too close to that edge would render with
  // its neighbourhood cut off, since there's no data beyond the boundary.
  const EUROPE_MIN_DEC = -35

  let loading = true
  let setupMode = true
  let allStars = []
  let starsById = new Map()
  let starsByHip = new Map()
  let starsByConst = new Map()
  let schemaHipSet = new Set()
  let conNameByAbbr = new Map()
  let constellationsMeta = null

  let scope = 'global'
  let difficulty = 'medium'
  let hasSaved = false
  let settingsLoaded = false

  let pool = []
  let mastery = {}
  let currentQuestion = null
  let options = []
  let revealLines = false
  let resolved = false // correct option has been tapped for the current question
  let firstTapMade = false // whether mastery has already been scored for this question
  let wrongTapped = new Set() // option ids tapped that were incorrect
  let feedback = ''
  let progressPct = 0

  let qRa0 = 0
  let qDec0 = 0
  let qFov = 25
  let fixedQuizFov = 60
  let qRenderMag = 5
  let qObjects = []
  let renderedTargetStar = null

  let currentQuestionConstellation = null
  let lineFallbackByHip = null

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

  function greekFromBayer(bayer) {
    const raw = String(bayer || '').trim()
    if (!raw) return null
    const first = raw.split(/\s+/)[0] || ''
    const cleaned = first
      .toLowerCase()
      .replace(/[0-9]+$/g, '')
      .replace(/[._-]+$/g, '')
    const greekChars = 'αβγδεζηθικλμνξοπρστυφχψω'
    if (cleaned && greekChars.includes(cleaned[0])) return cleaned[0]
    const key = cleaned.length >= 3 ? cleaned.slice(0, 3) : cleaned
    const map = {
      alf: 'α',
      alp: 'α',
      bet: 'β',
      gam: 'γ',
      del: 'δ',
      eps: 'ε',
      zet: 'ζ',
      eta: 'η',
      the: 'θ',
      iot: 'ι',
      kap: 'κ',
      lam: 'λ',
      mu: 'μ',
      nu: 'ν',
      xi: 'ξ',
      omi: 'ο',
      pi: 'π',
      rho: 'ρ',
      sig: 'σ',
      tau: 'τ',
      ups: 'υ',
      phi: 'φ',
      chi: 'χ',
      psi: 'ψ',
      ome: 'ω',
    }
    return map[key] || null
  }

  function preferredStarLabel(obj) {
    const rawName = String(obj?.name || '').trim()
    if (rawName) return rawName
    const rawBay = String(obj?.bay || '').trim()
    const greek = greekFromBayer(rawBay)
    if (greek && obj?.constellation) return `${greek} ${obj.constellation}`
    if (rawBay && obj?.constellation) return `${rawBay} ${obj.constellation}`
    if (obj?.hip != null) return `HIP ${obj.hip}`
    if (obj?.hd != null) return `HD ${obj.hd}`
    return String(obj?.id || 'Star')
  }

  function hasNameAndConstellation(s) {
    const hip = Number(s?.hip)
    const inSchema = schemaHipSet.size === 0 || (Number.isFinite(hip) && schemaHipSet.has(hip))
    return s?.type === 'star' && Array.isArray(s?.pos) && s.constellation && preferredStarLabel(s) && inSchema
  }

  function buildSchemaHipSet(constellations) {
    const out = new Set()
    if (!constellations || typeof constellations !== 'object') return out
    for (const con of Object.values(constellations)) {
      const lines = Array.isArray(con?.lines) ? con.lines : []
      for (const edge of lines) {
        if (!Array.isArray(edge) || edge.length < 2) continue
        const a = Number(edge[0])
        const b = Number(edge[1])
        if (Number.isFinite(a)) out.add(a)
        if (Number.isFinite(b)) out.add(b)
      }
    }
    return out
  }

  function computeLocalRadiusDeg() {
    return Math.max(25, (Number(viewFov) || 60) * 1.4)
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

  function buildPool(s, d) {
    const maxMag = DIFFICULTY_MAX_MAG[d] ?? DIFFICULTY_MAX_MAG.medium
    // A quiz view of fixedQuizFov centred on (or near) this star must not dip
    // below the catalogue's southern edge, or the rendered neighbourhood cuts
    // off abruptly with no stars beyond the boundary.
    const decFloor = EUROPE_MIN_DEC + fixedQuizFov / 2
    const base = allStars.filter((star) => {
      if (!hasNameAndConstellation(star)) return false
      const mag = Array.isArray(star.mag) ? star.mag[0] : Number(star.mag)
      if (!Number.isFinite(mag) || mag > maxMag) return false
      if (d === 'easy' && !String(star?.name || '').trim()) return false
      if (!Number.isFinite(star.pos?.[1]) || star.pos[1] < decFloor) return false
      if (s === 'local') {
        const dist = angSepDeg(star.pos, [viewRa0, viewDec0])
        if (!Number.isFinite(dist) || dist > computeLocalRadiusDeg()) return false
      }
      return true
    })
    return base.map((x) => x.id)
  }

  function computeConstellationView(star) {
    const group = starsByConst.get(star.constellation) || [star]
    let x = 0
    let y = 0
    let dec = 0
    for (const s of group) {
      const raRad = (s.pos[0] * Math.PI) / 180
      x += Math.cos(raRad)
      y += Math.sin(raRad)
      dec += s.pos[1]
    }
    const centerRa = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
    const centerDec = dec / group.length
    let span = 3
    for (const s of group) {
      span = Math.max(span, angSepDeg([centerRa, centerDec], s.pos))
    }
    const out = {
      ra0: centerRa,
      dec0: centerDec,
    }
    return out
  }

  function constellationRawFov(group) {
    if (!Array.isArray(group) || group.length === 0) return 20
    let x = 0
    let y = 0
    let dec = 0
    for (const s of group) {
      const raRad = (s.pos[0] * Math.PI) / 180
      x += Math.cos(raRad)
      y += Math.sin(raRad)
      dec += s.pos[1]
    }
    const centerRa = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
    const centerDec = dec / group.length
    let span = 3
    for (const s of group) {
      span = Math.max(span, angSepDeg([centerRa, centerDec], s.pos))
    }
    return span * 2.4
  }

  function computeFixedQuizFov() {
    let maxFov = 20
    for (const group of starsByConst.values()) {
      maxFov = Math.max(maxFov, constellationRawFov(group))
    }
    const umaRaw = constellationRawFov(starsByConst.get('UMa'))
    const anchorRaw = Number.isFinite(umaRaw) && umaRaw > 0 ? umaRaw : maxFov
    const fixed = Math.max(10, Math.min(120, anchorRaw * 0.735))
    return fixed
  }

  async function loadQuestionSky(star) {
    const view = computeConstellationView(star)
    qRa0 = view.ra0
    qDec0 = view.dec0
    qFov = fixedQuizFov
    const initialSep = angSepDeg([qRa0, qDec0], star.pos)
    const maxSafeSep = qFov * 0.45
    if (Number.isFinite(initialSep) && initialSep > maxSafeSep) {
      // Keep fixed zoom, but guarantee the asked star stays in-frame.
      qRa0 = star.pos[0]
      qDec0 = star.pos[1]
    }
    // Context depth is independent of quiz difficulty: pick a realistic random observing limit each question.
    const renderOptions = [4, 4.5, 5, 5.5, 6]
    qRenderMag = renderOptions[Math.floor(Math.random() * renderOptions.length)]
    const margin = Math.max(qFov * 1.2, 18)
    // Keep difficulty for selecting the asked star; context stars are rendered to qRenderMag.
    const queryMag = qRenderMag
    qObjects = await getObjectsInArea(qRa0 - margin, qRa0 + margin, qDec0 - margin, qDec0 + margin, queryMag)
  }

  function sampleIds(ids, n) {
    const arr = [...ids]
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[arr[i], arr[j]] = [arr[j], arr[i]]
    }
    return arr.slice(0, n)
  }

  function optionParts(starId) {
    const s = starsById.get(starId)
    const con = s?.constellation
    return {
      name: preferredStarLabel(s),
      constellation: (con && conNameByAbbr.get(con)) || con || '?',
    }
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
    saveQuizState(QUIZ_TYPE, difficulty, scope, {
      pool,
      mastery,
      currentQuestion,
    })
  }

  async function beginQuiz(continuePrev) {
    const freshPool = buildPool(scope, difficulty)
    if (freshPool.length < 4) {
      feedback = 'Not enough stars for this scope/difficulty. Try Global or easier level.'
      return
    }

    const saved = continuePrev ? loadQuizState(QUIZ_TYPE, difficulty, scope) : null
    if (saved?.pool?.length >= 4) {
      // Resume the exact star selection from the saved quiz, not a fresh sample.
      const validPool = saved.pool.filter((id) => freshPool.includes(id))
      pool = validPool.length >= 4 ? validPool : sampleIds(freshPool, QUIZ_POOL_SIZE)
      mastery = { ...(saved.mastery || {}) }
      currentQuestion = pool.includes(saved.currentQuestion) ? saved.currentQuestion : pickNextQuestion(pool, mastery)
    } else {
      // New quiz: pick a fresh, fixed-size random sample so the quiz has a definite end.
      pool = sampleIds(freshPool, QUIZ_POOL_SIZE)
      mastery = {}
      currentQuestion = pickNextQuestion(pool, mastery)
      clearQuizState(QUIZ_TYPE, difficulty, scope)
    }

    progressPct = computeProgressPct(pool, mastery)
    setupMode = false
    revealLines = false
    resolved = false
    firstTapMade = false
    wrongTapped = new Set()
    feedback = ''
    pickOptions(currentQuestion)
    await loadQuestionSky(starsById.get(currentQuestion))
    saveState()
  }

  async function nextQuestion() {
    revealLines = false
    resolved = false
    firstTapMade = false
    wrongTapped = new Set()
    feedback = ''
    currentQuestion = pickNextQuestion(pool, mastery)
    if (!currentQuestion) return
    pickOptions(currentQuestion)
    await loadQuestionSky(starsById.get(currentQuestion))
    saveState()
  }

  async function handleAnswer(optionId) {
    if (!currentQuestion) return
    if (resolved) {
      // Re-tapping the highlighted correct option advances to the next question.
      if (optionId === currentQuestion && progressPct < 100) await nextQuestion()
      return
    }
    if (wrongTapped.has(optionId)) return
    revealLines = true
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

  function handleSkyTap() {
    if (resolved && progressPct < 100) nextQuestion()
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

  $: renderedTargetStar =
    qObjects.find((o) => o?.id === currentQuestion && Array.isArray(o?.pos)) || starsById.get(currentQuestion) || null
  $: currentQuestionConstellation =
    renderedTargetStar?.constellation || starsById.get(currentQuestion)?.constellation || null
  // Resolve fallback positions directly from the line schema's own HIP
  // references, rather than via starsByConst's constellation-membership
  // match — a star can be a genuine vertex of a constellation's line figure
  // while its own catalogued `constellation` field (from a different source)
  // doesn't exactly match that constellation's abbreviation. Requiring an
  // exact match silently dropped some line endpoints, breaking lines that
  // should always be fully drawable once revealed.
  $: lineFallbackByHip = (() => {
    if (!revealLines || !currentQuestionConstellation) return null
    const con = constellationsMeta?.[currentQuestionConstellation]
    const lines = Array.isArray(con?.lines) ? con.lines : []
    if (lines.length === 0) return null
    const map = new Map()
    for (const edge of lines) {
      if (!Array.isArray(edge) || edge.length < 2) continue
      for (const hip of [Number(edge[0]), Number(edge[1])]) {
        if (!Number.isFinite(hip) || map.has(hip)) continue
        const s = starsByHip.get(hip)
        if (s && Array.isArray(s.pos)) map.set(hip, s.pos)
      }
    }
    return map
  })()

  onMount(() => {
    window.addEventListener('keydown', onGlobalKeyDown, true)
    ;(async () => {
      loadQuizSettings()
      settingsLoaded = true
      const [index, constellations] = await Promise.all([getSearchIndex(), getMeta('constellations')])
      constellationsMeta = constellations
      schemaHipSet = buildSchemaHipSet(constellations)
      if (constellations && typeof constellations === 'object') {
        const names = new Map()
        for (const [abbr, con] of Object.entries(constellations)) {
          if (con?.name) names.set(abbr, con.name)
        }
        conNameByAbbr = names
      }
      const sourceStars = index.filter((x) => x.type === 'star' && Array.isArray(x.pos))
      allStars = sourceStars.filter((s) => hasNameAndConstellation(s))
      starsById = new Map(allStars.map((s) => [s.id, s]))
      const nextStarsByHip = new Map()
      for (const s of allStars) {
        const hip = Number(s?.hip)
        if (Number.isFinite(hip)) nextStarsByHip.set(hip, s)
      }
      starsByHip = nextStarsByHip
      const grouped = new Map()
      if (constellations && typeof constellations === 'object') {
        for (const [abbr, con] of Object.entries(constellations)) {
          const hips = new Set()
          const lines = Array.isArray(con?.lines) ? con.lines : []
          for (const edge of lines) {
            if (!Array.isArray(edge) || edge.length < 2) continue
            const a = Number(edge[0])
            const b = Number(edge[1])
            if (Number.isFinite(a)) hips.add(a)
            if (Number.isFinite(b)) hips.add(b)
          }
          const stars = []
          for (const hip of hips) {
            const s = starsByHip.get(hip)
            if (s && s.constellation === abbr) stars.push(s)
          }
          if (stars.length > 0) grouped.set(abbr, stars)
        }
      }
      // Fallback when schema metadata is unavailable: group by star.constellation.
      if (grouped.size === 0) {
        for (const s of allStars) {
          if (!s.constellation) continue
          if (!grouped.has(s.constellation)) grouped.set(s.constellation, [])
          grouped.get(s.constellation).push(s)
        }
      }
      starsByConst = grouped
      fixedQuizFov = computeFixedQuizFov()
      loading = false
    })()
  })

  onDestroy(() => {
    window.removeEventListener('keydown', onGlobalKeyDown, true)
  })
</script>

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={handleBack} aria-label="Back">
      <BackIcon size="1.2rem" aria-hidden="true" />
    </button>
    <span class="title">Constellation Quiz</span>
  </div>

  <div class="body">
    {#if loading}
      <p class="msg">Loading star index...</p>
    {:else if setupMode}
      <QuizSetup
        title="Constellation Quiz"
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
      <QuizProgress {progressPct} />

      <p class="question">
        {resolved && progressPct < 100 ? 'Tap the sky for the next question' : 'Which star is highlighted?'}
      </p>
      <div
        class="sky-wrap"
        class:tappable={resolved && progressPct < 100}
        role="button"
        tabindex="0"
        on:click={handleSkyTap}
        on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && handleSkyTap()}
      >
        <SkyCanvas
          ra0={qRa0}
          dec0={qDec0}
          fov={qFov}
          objects={qObjects}
          starRadiusScale={2}
          targetMarker={Array.isArray(renderedTargetStar?.pos) ? renderedTargetStar.pos : null}
          targetMarkerColor="rgba(120,0,255,0.9)"
          {lineFallbackByHip}
          constellationLineColorOverride={revealLines && $theme !== 'nightly' ? 'rgba(255,0,255,0.85)' : null}
          magLimitOverride={qRenderMag}
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
          {@const parts = optionParts(oid)}
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
            <span class="answer-label"><strong>{parts.name}</strong> ({parts.constellation})</span>
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

  .sky-wrap {
    position: relative;
    width: 100%;
    max-width: 520px;
    aspect-ratio: 1 / 1;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid rgba(180, 0, 0, 0.45);
    align-self: center;
  }

  .sky-wrap.tappable {
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
