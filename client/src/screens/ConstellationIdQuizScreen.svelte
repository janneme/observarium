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
  import { clearQuizState, loadQuizState, saveQuizState } from '../lib/quizFramework.js'

  export let lat = 48.2
  export let lon = 16.37
  export let time = new Date()

  const dispatch = createEventDispatcher()
  const QUIZ_TYPE = 'constellation_id'
  const QUIZ_SETTINGS_KEY = 'observarium.constellationIdQuiz.settings'

  const QUIZ_FOV_DEG = 90
  const VISUAL_RANGE_MIN = 3.5
  const VISUAL_RANGE_MAX = 5.5
  const SCHEMA_VISIBILITY_MIN_FRACTION = 0.8
  const QUIZ_QUESTION_COUNT = 20
  const EASY_MIN_BRIGHT_MAG = 2
  const MEDIUM_MIN_BRIGHT_MAG = 3.5
  const DISTRACTOR_SIZE_RATIO_MAX = 2.5
  const DISTRACTOR_MAG_DELTA_MAX = 1.5
  // Mirrors data_prep/config.py: star catalogue only covers dec >= -35°. Views
  // whose southern edge would fall below this must be shifted north.
  const EUROPE_MIN_DEC = -35

  let loading = true
  let setupMode = true
  let allStars = []
  let starsByHip = new Map()
  let conInfoByAbbr = new Map()
  let conNameByAbbr = new Map()
  let schemaFallbackByHip = null

  let scope = 'global'
  let difficulty = 'medium'
  let hasSaved = false
  let settingsLoaded = false

  let pool = []
  // Per-question progress. mastery[abbr] = { chain, everWrong }.
  //   chain      = consecutive first-attempt-correct answers since the last
  //                incorrect first attempt (or since the quiz began).
  //   everWrong  = whether this question has ever been answered incorrectly
  //                on the first attempt; once true, needs `chain >= 3` to pass
  //                (a single lucky guess shouldn't pass a question the user
  //                doesn't actually know).
  // A never-wrong question needs `chain >= 2` (two correct attempts in a
  // row) to pass.
  let mastery = {}
  let currentQuestion = null
  let options = []
  let optionsUseAbbrev = false
  let resolved = false
  let firstTapMade = false
  let wrongTapped = new Set()
  let feedback = ''

  let qRa0 = 0
  let qDec0 = 0
  let qFov = QUIZ_FOV_DEG
  let qRotation = 0
  let qRenderMag = 5
  let qObjects = []
  let qObjectsFiltered = []

  function questionState(abbr) {
    return mastery[abbr] || { chain: 0, everWrong: false }
  }
  function required(state) {
    return state.everWrong ? 3 : 2
  }
  function questionScore(state) {
    const req = required(state)
    if (state.chain >= req) return 1
    return state.chain / req
  }
  function isPassed(abbr) {
    return questionScore(questionState(abbr)) >= 1
  }
  function applyAttempt(m, abbr, correct) {
    const prev = m[abbr] || { chain: 0, everWrong: false }
    if (correct) return { ...m, [abbr]: { chain: prev.chain + 1, everWrong: prev.everWrong } }
    return { ...m, [abbr]: { chain: 0, everWrong: true } }
  }

  // Progress is achieved / required across the whole pool. Each question's
  // `required` starts at 2 and becomes 3 as soon as it has been answered
  // incorrectly once (a first-attempt wrong flips `everWrong` to true). So a
  // wrong first attempt lowers the whole progress by growing the denominator
  // without adding to the numerator, which shows visibly on the progress bar.
  // References to `pool` and `mastery` are literal so Svelte's reactivity
  // picks up mutations to either.
  $: progressPct = ((m, p) => {
    if (!p.length) return 0
    let achieved = 0
    let totalReq = 0
    for (const abbr of p) {
      const s = m[abbr] || { chain: 0, everWrong: false }
      const req = s.everWrong ? 3 : 2
      totalReq += req
      achieved += Math.min(s.chain, req)
    }
    return totalReq > 0 ? (achieved / totalReq) * 100 : 0
  })(mastery, pool)
  $: allPassed =
    pool.length > 0 &&
    pool.every((abbr) => {
      const s = mastery[abbr] || { chain: 0, everWrong: false }
      return s.chain >= (s.everWrong ? 3 : 2)
    })

  function updateHasSaved() {
    hasSaved = !!loadQuizState(QUIZ_TYPE, difficulty, scope)
  }

  function loadQuizSettings() {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage?.getItem(QUIZ_SETTINGS_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw)
      const d = String(parsed?.difficulty || '')
      if (d === 'easy' || d === 'medium' || d === 'hard') difficulty = d
    } catch {
      return
    }
  }

  function saveQuizSettings(nextDifficulty) {
    if (typeof window === 'undefined') return
    try {
      window.localStorage?.setItem(QUIZ_SETTINGS_KEY, JSON.stringify({ difficulty: nextDifficulty }))
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

  function circularMeanRa(ras) {
    let x = 0
    let y = 0
    for (const ra of ras) {
      const r = (ra * Math.PI) / 180
      x += Math.cos(r)
      y += Math.sin(r)
    }
    return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
  }

  function buildConInfo(constellations) {
    const info = new Map()
    if (!constellations || typeof constellations !== 'object') return info
    for (const [abbr, con] of Object.entries(constellations)) {
      const lines = Array.isArray(con?.lines) ? con.lines : []
      const hipSet = new Set()
      for (const edge of lines) {
        if (!Array.isArray(edge) || edge.length < 2) continue
        const a = Number(edge[0])
        const b = Number(edge[1])
        if (Number.isFinite(a)) hipSet.add(a)
        if (Number.isFinite(b)) hipSet.add(b)
      }
      const schemaStars = []
      for (const hip of hipSet) {
        const s = starsByHip.get(hip)
        if (!s || !Array.isArray(s.pos)) continue
        const m = Array.isArray(s.mag) ? s.mag[0] : Number(s.mag)
        if (!Number.isFinite(m)) continue
        schemaStars.push({ hip, ra: s.pos[0], dec: s.pos[1], mag: m })
      }
      if (schemaStars.length < 2) continue
      const ras = schemaStars.map((s) => s.ra)
      const centroidRa = circularMeanRa(ras)
      const centroidDec = schemaStars.reduce((sum, s) => sum + s.dec, 0) / schemaStars.length
      let angularSize = 0
      for (let i = 0; i < schemaStars.length; i++) {
        for (let j = i + 1; j < schemaStars.length; j++) {
          const sep = angSepDeg([schemaStars[i].ra, schemaStars[i].dec], [schemaStars[j].ra, schemaStars[j].dec])
          if (sep > angularSize) angularSize = sep
        }
      }
      const sortedMags = schemaStars.map((s) => s.mag).sort((a, b) => a - b)
      const brightestMag = sortedMags[0]
      const kMin = Math.ceil(SCHEMA_VISIBILITY_MIN_FRACTION * sortedMags.length)
      const thresholdMag = sortedMags[Math.max(0, kMin - 1)]
      // Southern- and northernmost boundary vertices: these determine whether
      // a candidate (dec0, rotation) pair fits the whole boundary inside the
      // view (without missing-data intrusion at the south). Schema-star
      // extent alone is not enough — e.g. Sagittarius's schema stars stop at
      // ~-34° but its IAU boundary reaches to ~-45°.
      let boundaryMinDec = Infinity
      let boundaryMaxDec = -Infinity
      const bounds = Array.isArray(con?.bounds) ? con.bounds : []
      for (const seg of bounds) {
        if (!Array.isArray(seg)) continue
        for (const v of seg) {
          if (Array.isArray(v) && Number.isFinite(v[1])) {
            if (v[1] < boundaryMinDec) boundaryMinDec = v[1]
            if (v[1] > boundaryMaxDec) boundaryMaxDec = v[1]
          }
        }
      }
      info.set(abbr, {
        abbr,
        name: con.name || abbr,
        schemaHips: [...hipSet],
        schemaStars,
        centroidRa,
        centroidDec,
        angularSize,
        brightestMag,
        thresholdMag,
        boundaryMinDec,
        boundaryMaxDec,
      })
    }
    return info
  }

  // Half-diagonal (corner) and half-edge (edge-midpoint) angular offsets of
  // the square canvas from its centre, in degrees. For FOV=90° these are
  // arctan(a·√2) ≈ 48.00° and arctan(a) ≈ 38.15° with a = fovRad/2.
  const FOV_RAD = (QUIZ_FOV_DEG * Math.PI) / 180
  const CANVAS_HALF_A = FOV_RAD / 2
  const C_MIN_DEG = (Math.atan(CANVAS_HALF_A) * 180) / Math.PI
  const C_MAX_DEG = (Math.atan(CANVAS_HALF_A * Math.SQRT2) * 180) / Math.PI

  // Sky-dec-range constraints for a canvas centred at dec0 with rotation R:
  //   min sky dec on canvas = dec0 - c(R)
  //   max sky dec on canvas = dec0 + c(R)
  // where c(R) = arctan(a / max(|sin R|, |cos R|)) is monotone in R between
  // C_MIN_DEG (edge midpoint at south) and C_MAX_DEG (corner at south).
  //
  // Returns the [decLow, decHigh] range of centre dec such that some rotation
  // makes the canvas both (a) contain the entire constellation boundary and
  // (b) not include any sky south of EUROPE_MIN_DEC. Returns null if no dec0
  // works — e.g. the boundary itself extends below the data floor.
  function validDec0Range(info) {
    if (!Number.isFinite(info.boundaryMinDec) || info.boundaryMinDec < EUROPE_MIN_DEC) return null
    const decLow = Math.max(
      EUROPE_MIN_DEC + C_MIN_DEG,
      info.boundaryMaxDec - C_MAX_DEG,
      (info.boundaryMaxDec + EUROPE_MIN_DEC) / 2,
    )
    const decHigh = info.boundaryMinDec + C_MAX_DEG
    if (decHigh < decLow) return null
    return [decLow, decHigh]
  }

  function isEligible(info, d) {
    if (d === 'easy' && info.brightestMag >= EASY_MIN_BRIGHT_MAG) return false
    if (d === 'medium' && info.brightestMag >= MEDIUM_MIN_BRIGHT_MAG) return false
    const minSatisfying = Math.max(info.thresholdMag, VISUAL_RANGE_MIN)
    if (minSatisfying > VISUAL_RANGE_MAX) return false
    if (!validDec0Range(info)) return false
    return true
  }

  function buildPool(d) {
    const eligible = []
    const excluded = []
    for (const info of conInfoByAbbr.values()) {
      if (isEligible(info, d)) eligible.push(info.abbr)
      else excluded.push(info.abbr)
    }
    console.log(
      `@@ [ConstQuiz] buildPool difficulty=${d} eligible=${eligible.length} excluded=${excluded.length} [${excluded.join(',')}]`,
    )
    return eligible
  }

  function shuffle(arr) {
    const out = [...arr]
    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[out[i], out[j]] = [out[j], out[i]]
    }
    return out
  }

  function pickDistractors(correctAbbr, d) {
    const info = conInfoByAbbr.get(correctAbbr)
    const all = [...conInfoByAbbr.keys()].filter((abbr) => abbr !== correctAbbr)
    if (d === 'easy') {
      return shuffle(all).slice(0, 3)
    }
    let sizeMax = DISTRACTOR_SIZE_RATIO_MAX
    let magMax = DISTRACTOR_MAG_DELTA_MAX
    for (let attempt = 0; attempt < 6; attempt++) {
      const filtered = all.filter((abbr) => {
        const other = conInfoByAbbr.get(abbr)
        if (!other) return false
        const a = info.angularSize
        const b = other.angularSize
        if (a <= 0 || b <= 0) return false
        const ratio = Math.max(a, b) / Math.min(a, b)
        if (ratio > sizeMax) return false
        if (Math.abs(info.brightestMag - other.brightestMag) > magMax) return false
        return true
      })
      if (filtered.length >= 3) return shuffle(filtered).slice(0, 3)
      sizeMax *= 1.5
      magMax *= 1.5
    }
    return shuffle(all).slice(0, 3)
  }

  function computeViewCenter(info) {
    // The valid dec0 range is guaranteed non-empty because ineligible
    // constellations were filtered out at pool-build time. Clamp the centroid
    // into that range so we stay as close to a centred view as possible.
    const range = validDec0Range(info)
    const ra0 = info.centroidRa
    const dec0 = Math.max(range[0], Math.min(range[1], info.centroidDec))

    // Rotation must keep every canvas boundary point in data-covered sky and
    // inside the constellation's boundary extent. Concretely, c(R) must lie
    // in [cLow, cHigh] where c(R) = arctan(a / max(|sin R|, |cos R|)) in
    // degrees. Convert that to a range of m = max(|sin R|, |cos R|) and
    // reject-sample R uniformly until one lands in that range.
    const cLow = Math.max(C_MIN_DEG, dec0 - info.boundaryMinDec, info.boundaryMaxDec - dec0)
    const cHigh = Math.min(C_MAX_DEG, dec0 - EUROPE_MIN_DEC)
    // Larger c → smaller m, so mMin comes from cHigh and mMax from cLow.
    const mMin = Math.max(1 / Math.SQRT2, CANVAS_HALF_A / Math.tan((cHigh * Math.PI) / 180))
    const mMax = Math.min(1, CANVAS_HALF_A / Math.tan((cLow * Math.PI) / 180))
    let rotation = 0
    let attempts = 0
    for (attempts = 1; attempts <= 500; attempts++) {
      const R = Math.random() * Math.PI * 2
      const m = Math.max(Math.abs(Math.sin(R)), Math.abs(Math.cos(R)))
      if (m >= mMin && m <= mMax) {
        rotation = R
        break
      }
    }
    if (attempts > 500) {
      // Deterministic fallback: pick c at midpoint of allowed range, then an
      // R whose m matches. Randomise which of the 8 equivalent quadrant
      // solutions we land on so the fallback isn't visually predictable.
      const cMid = (cLow + cHigh) / 2
      const mTarget = CANVAS_HALF_A / Math.tan((cMid * Math.PI) / 180)
      const base = Math.acos(Math.min(1, Math.max(-1, mTarget)))
      const quadrant = Math.floor(Math.random() * 4)
      const flip = Math.random() < 0.5
      rotation = quadrant * (Math.PI / 2) + (flip ? Math.PI / 2 - base : base)
    }

    console.log(
      `@@ [ConstQuiz] computeViewCenter abbr=${info.abbr} centroidDec=${info.centroidDec.toFixed(2)} boundaryDec=[${info.boundaryMinDec.toFixed(2)}, ${info.boundaryMaxDec.toFixed(2)}] dec0=${dec0.toFixed(2)} rotDeg=${((rotation * 180) / Math.PI).toFixed(1)} cRange=[${cLow.toFixed(2)}, ${cHigh.toFixed(2)}] mRange=[${mMin.toFixed(3)}, ${mMax.toFixed(3)}] attempts=${attempts}`,
    )
    return { ra0, dec0, rotation }
  }

  function pickVisualRange(info) {
    const minSatisfying = Math.max(info.thresholdMag, VISUAL_RANGE_MIN)
    if (minSatisfying > VISUAL_RANGE_MAX) return null
    return minSatisfying + Math.random() * (VISUAL_RANGE_MAX - minSatisfying)
  }

  async function loadQuestionSky(abbr) {
    const info = conInfoByAbbr.get(abbr)
    if (!info) return
    const view = computeViewCenter(info)
    qRa0 = view.ra0
    qDec0 = view.dec0
    qRotation = view.rotation
    qFov = QUIZ_FOV_DEG
    qRenderMag = pickVisualRange(info) ?? VISUAL_RANGE_MAX
    console.log(
      `@@ [ConstQuiz] loadQuestionSky abbr=${abbr} difficulty=${difficulty} qRa0=${qRa0.toFixed(2)} qDec0=${qDec0.toFixed(2)} qRenderMag=${qRenderMag.toFixed(2)} brightest=${info.brightestMag.toFixed(2)} threshold=${info.thresholdMag.toFixed(2)} angularSize=${info.angularSize.toFixed(2)} schemaStars=${info.schemaStars.length}`,
    )

    const margin = QUIZ_FOV_DEG * 0.9
    const cosDec = Math.max(0.05, Math.cos((qDec0 * Math.PI) / 180))
    const raMargin = Math.min(180, margin / cosDec)
    qObjects = await getObjectsInArea(qRa0 - raMargin, qRa0 + raMargin, qDec0 - margin, qDec0 + margin, qRenderMag)
    updateFilteredObjects()
    console.log(`@@ [ConstQuiz] loadQuestionSky loaded ${qObjects.length} objects, filtered=${qObjectsFiltered.length}`)
  }

  function updateFilteredObjects() {
    if (difficulty !== 'hard' || firstTapMade || !currentQuestion) {
      qObjectsFiltered = qObjects
      return
    }
    const info = conInfoByAbbr.get(currentQuestion)
    const hipSet = new Set(info?.schemaHips || [])
    qObjectsFiltered = qObjects.filter((o) => {
      if (o?.type !== 'star' && o?.type !== 'double_star') return true
      const hip = Number(o?.hip)
      return !Number.isFinite(hip) || !hipSet.has(hip)
    })
  }

  function pickOptions(correctAbbr) {
    const distractors = pickDistractors(correctAbbr, difficulty)
    const chosen = shuffle([correctAbbr, ...distractors])
    options = chosen
    // Easy always uses full names; Medium/Hard randomly pick names or abbrs.
    optionsUseAbbrev = difficulty !== 'easy' && Math.random() < 0.5
    console.log(
      `@@ [ConstQuiz] pickOptions correct=${correctAbbr} options=${chosen.join(',')} useAbbrev=${optionsUseAbbrev}`,
    )
  }

  $: optionLabels = options.map((abbr) => (optionsUseAbbrev ? abbr : conNameByAbbr.get(abbr) || abbr))

  function saveState() {
    saveQuizState(QUIZ_TYPE, difficulty, scope, {
      pool,
      mastery,
      currentQuestion,
    })
  }

  // Pick the next unpassed question. Prefer those with the lowest score so
  // partly-progressed retries don't dominate; use random tie-breaking so
  // question order stays varied. If possible, avoid the just-answered question
  // to give the user a temporal gap before its next re-ask.
  function pickNextUnpassed(excludeAbbr) {
    const unpassed = pool.filter((abbr) => !isPassed(abbr))
    if (unpassed.length === 0) return null
    const others = unpassed.filter((abbr) => abbr !== excludeAbbr)
    const searchIn = others.length > 0 ? others : unpassed
    const scored = searchIn.map((abbr) => ({ abbr, score: questionScore(questionState(abbr)) }))
    const minScore = Math.min(...scored.map((s) => s.score))
    const candidates = scored.filter((s) => s.score === minScore).map((s) => s.abbr)
    return candidates[Math.floor(Math.random() * candidates.length)]
  }

  async function beginQuiz(continuePrev) {
    const freshPool = buildPool(difficulty)
    if (freshPool.length < 4) {
      feedback = 'Not enough constellations for this difficulty.'
      return
    }

    const saved = continuePrev ? loadQuizState(QUIZ_TYPE, difficulty, scope) : null
    if (saved?.pool?.length >= 4 && saved.pool.every((abbr) => freshPool.includes(abbr))) {
      pool = saved.pool
      mastery = saved.mastery && typeof saved.mastery === 'object' ? { ...saved.mastery } : {}
      currentQuestion = pool.includes(saved.currentQuestion) ? saved.currentQuestion : pickNextUnpassed(null)
    } else {
      const shuffled = shuffle(freshPool)
      pool = shuffled.slice(0, Math.min(QUIZ_QUESTION_COUNT, shuffled.length))
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
      await loadQuestionSky(currentQuestion)
    }
    saveState()
  }

  async function nextQuestion() {
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
    await loadQuestionSky(currentQuestion)
    saveState()
  }

  async function handleAnswer(optionAbbr) {
    if (!currentQuestion) return
    if (resolved) {
      if (optionAbbr === currentQuestion && !allPassed) await nextQuestion()
      return
    }
    if (wrongTapped.has(optionAbbr)) return
    const correct = optionAbbr === currentQuestion
    if (!firstTapMade) {
      firstTapMade = true
      mastery = applyAttempt(mastery, currentQuestion, correct)
      updateFilteredObjects()
    }
    if (correct) {
      resolved = true
    } else {
      wrongTapped = new Set([...wrongTapped, optionAbbr])
    }
    saveState()
  }

  async function handleSkyTap() {
    if (resolved && !allPassed) await nextQuestion()
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
  $: if (setupMode && settingsLoaded) saveQuizSettings(difficulty)

  // Line-set-scope per difficulty and reveal state.
  // Easy: exclude quizzed until reveal, then all. Medium/Hard: none until reveal, then all.
  $: lineAbbrsFilter = firstTapMade ? 'all' : difficulty === 'easy' ? 'exclude-quizzed' : 'none'

  onMount(() => {
    window.addEventListener('keydown', onGlobalKeyDown, true)
    ;(async () => {
      loadQuizSettings()
      settingsLoaded = true
      const [index, constellations] = await Promise.all([getSearchIndex(), getMeta('constellations')])
      const nameMap = new Map()
      if (constellations && typeof constellations === 'object') {
        for (const [abbr, con] of Object.entries(constellations)) {
          if (con?.name) nameMap.set(abbr, con.name)
        }
      }
      conNameByAbbr = nameMap
      allStars = index.filter((x) => x.type === 'star' && Array.isArray(x.pos))
      const nextStarsByHip = new Map()
      for (const s of allStars) {
        const hip = Number(s?.hip)
        if (Number.isFinite(hip)) nextStarsByHip.set(hip, s)
      }
      starsByHip = nextStarsByHip
      conInfoByAbbr = buildConInfo(constellations)
      // Build a global HIP → [ra, dec] fallback so SkyCanvas can draw any
      // constellation line whose endpoint is fainter than the quiz's visual
      // range and therefore absent from the loaded `objects` array.
      const fallback = new Map()
      for (const info of conInfoByAbbr.values()) {
        for (const s of info.schemaStars) {
          if (!fallback.has(s.hip)) fallback.set(s.hip, [s.ra, s.dec])
        }
      }
      schemaFallbackByHip = fallback
      console.log(
        `@@ [ConstQuiz] onMount ready: ${conInfoByAbbr.size} constellations, ${fallback.size} schema HIPs in fallback`,
      )
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
      <p class="msg">Loading constellations...</p>
    {:else if setupMode}
      <QuizSetup
        title="Constellation Quiz"
        {hasSaved}
        initialDifficulty={difficulty}
        initialScope={scope}
        allowLocal={false}
        showScope={false}
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

      {#if allPassed || !currentQuestion}
        <p class="done">Congratulations on completing the quiz!</p>
      {:else}
        <p class="question">
          {resolved ? 'Tap the sky for the next question' : 'Which constellation is this?'}
        </p>
        <div
          class="sky-wrap"
          class:tappable={resolved}
          role="button"
          tabindex="0"
          on:click={handleSkyTap}
          on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && handleSkyTap()}
        >
          <SkyCanvas
            ra0={qRa0}
            dec0={qDec0}
            fov={qFov}
            rotation={qRotation}
            objects={qObjectsFiltered}
            lineFallbackByHip={schemaFallbackByHip}
            starRadiusScale={1.5}
            constellationLineColorOverride={$theme === 'nightly' ? '#0000ff' : 'rgba(140,180,255,0.9)'}
            magLimitOverride={qRenderMag}
            {lat}
            {lon}
            {time}
            finderMode={false}
            showFovCircle={false}
            showConstellationLines={lineAbbrsFilter !== 'none'}
            {lineAbbrsFilter}
            quizzedConstellationAbbr={currentQuestion}
            showConstellationNames={false}
            showConstellationBoundaries={true}
            highlightBoundaryAbbr={currentQuestion}
            showDsos={false}
            showSpecialStarSymbols={false}
            showHorizon={false}
            showSolarSystem={false}
          />
        </div>

        <div class="answers">
          {#each options as abbr, i}
            {@const isCorrect = abbr === currentQuestion}
            {@const isWrongTapped = wrongTapped.has(abbr)}
            {@const isSkipped = resolved && !isCorrect && !isWrongTapped}
            <button
              class="answer"
              class:correct={resolved && isCorrect}
              class:wrong={isWrongTapped}
              class:skipped={isSkipped}
              disabled={isWrongTapped || isSkipped}
              on:click={() => handleAnswer(abbr)}
            >
              <span class="answer-label"><strong>{optionLabels[i]}</strong></span>
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
    margin: 1.2rem 0;
    color: #3366ff;
    font-size: 1.6rem;
    font-weight: 700;
    text-align: center;
  }

  :global([data-theme='nightly']) .done {
    color: #0000ff;
  }
</style>
