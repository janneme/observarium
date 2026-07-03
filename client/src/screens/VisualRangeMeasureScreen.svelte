<script>
  import { createEventDispatcher } from 'svelte'
  import { getTodayObservation, putObservation, getObjectsInArea } from '../lib/db.js'
  import SkyCanvas from '../components/SkyCanvas.svelte'

  export let lat = 0
  export let lon = 0
  export let time = new Date()
  export let plan = null
  export let startStar = null
  export let telescope = null
  export let eyepiece = null
  export let initialMag = 8.0

  const dispatch = createEventDispatcher()
  const MEASURE_STEP = 0.5

  function getStarMag(star) {
    return typeof star.mag === 'number' ? star.mag : star.mag[0]
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
    if (!obj) return 'Star'
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

  function _hasRealLabel(obj) {
    if (!obj) return false
    if (String(obj?.name || '').trim()) return true
    const rawBay = String(obj?.bay || '').trim()
    if (rawBay && obj?.constellation) return true
    if (obj?.hip != null) return true
    if (obj?.hd != null) return true
    return false
  }

  function formatTime(t) {
    if (!t) return ''
    const d = t instanceof Date ? t : new Date(t)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  $: fovDeg = eyepiece && telescope ? (eyepiece.fovDeg * eyepiece.focalLengthMm) / telescope.focalLengthMm : 5

  let stepIndex = 0
  let moveIndex = 0
  let phase = 'move' // 'move' | 'test' | 'result'
  let candidateSlot = 0
  let currentMag = initialMag - MEASURE_STEP
  let viewCentre = startStar?.pos ?? [0, 0]
  let historyStack = []
  let resultLogged = false
  let logConfirmMsg = ''

  let _starObjects = []
  let _starLoadId = 0

  async function _loadStarsForView(centre, fov, magLim) {
    const id = ++_starLoadId
    const [ra0q, dec0q] = centre
    const decMin = Math.max(-90, dec0q - fov)
    const decMax = Math.min(90, dec0q + fov)
    const cosD = Math.max(0.05, Math.cos((dec0q * Math.PI) / 180))
    const raSpan = fov / cosD
    const items = await getObjectsInArea(ra0q - raSpan, ra0q + raSpan, decMin, decMax, magLim)
    if (id !== _starLoadId) return
    _starObjects = items
      .filter((o) => o.type === 'star' || o.type === 'double_star')
      .map((o) => ({
        ...o,
        type: 'star',
        dbl: undefined,
        pairs: undefined,
        mag: Array.isArray(o.mag) ? o.mag[0] : o.mag,
      }))
  }

  $: if (viewCentre && fovDeg > 0) _loadStarsForView(viewCentre, fovDeg, magLimitForView)

  // Precompute the telescope's starting position for each step by applying
  // moves sequentially. step.centre is the DSO pair midpoint (navigation target),
  // which differs from the actual computed endpoint of the moves.
  const _stepStarts = (() => {
    const starts = [startStar?.pos ?? [0, 0]]
    if (plan?.steps) {
      for (let i = 0; i < plan.steps.length - 1; i++) {
        let pos = starts[i]
        for (const m of plan.steps[i].moves) {
          pos = [
            pos[0] + m.multiplier * (m.to.pos[0] - m.from.pos[0]),
            pos[1] + m.multiplier * (m.to.pos[1] - m.from.pos[1]),
          ]
        }
        starts.push(pos)
      }
    }
    return starts
  })()
  console.log(
    '[VR] plan stepStarts:',
    _stepStarts.map((p, i) => `[${i}] RA=${p[0].toFixed(3)} Dec=${p[1].toFixed(3)}`),
  )
  if (plan?.steps) {
    plan.steps.forEach((s, i) =>
      console.log(
        `[VR] step[${i}] centre=(RA=${s.centre[0].toFixed(3)} Dec=${s.centre[1].toFixed(3)}) numMoves=${s.moves.length} candidates=[${s.candidates.map((c) => `id=${c.id} mag=${getStarMag(c).toFixed(2)}`).join(', ')}]`,
      ),
    )
  }

  // Synchronous init — set phase and viewCentre from first step
  const _firstStep = plan?.steps?.[0]
  if (!_firstStep) {
    phase = 'result'
  } else if (_firstStep.moves.length === 0) {
    phase = 'test'
    viewCentre = _stepStarts[0] ?? startStar?.pos ?? [0, 0]
  }
  // else: phase='move', viewCentre=startStar.pos (already set at declaration)

  $: currentStep = plan?.steps?.[stepIndex] ?? null
  $: currentMove = phase === 'move' && currentStep ? currentStep.moves[moveIndex] : null
  $: currentCandidate = phase === 'test' && currentStep ? currentStep.candidates[candidateSlot] : null

  $: magLimitForView = (() => {
    if (phase === 'result' || !currentStep) return currentMag + 0.5
    return getStarMag(currentStep.candidates[0]) + 0.5
  })()

  $: guideArrows = (() => {
    if (phase === 'move' && currentMove) {
      return [
        {
          fromRa: currentMove.from.pos[0],
          fromDec: currentMove.from.pos[1],
          toRa: currentMove.to.pos[0],
          toDec: currentMove.to.pos[1],
          label: currentMove.multiplier > 1 ? `×${currentMove.multiplier}` : undefined,
        },
      ]
    }
    if (phase === 'test' && currentCandidate) {
      return [{ markerRa: currentCandidate.pos[0], markerDec: currentCandidate.pos[1] }]
    }
    return []
  })()

  $: instructionText = (() => {
    if (phase === 'move' && currentMove) {
      const fromLbl = preferredStarLabel(currentMove.from)
      const toLbl = preferredStarLabel(currentMove.to)
      const k = currentMove.multiplier
      return k > 1
        ? `Find ${fromLbl} → ${toLbl}, then hop ×${k} that distance onward`
        : `Use ${fromLbl} → ${toLbl} to reach the next field`
    }
    if (phase === 'test' && currentCandidate) {
      if (_hasRealLabel(currentCandidate)) {
        return `Can you see ${preferredStarLabel(currentCandidate)}?`
      }
      return 'Can you see this star?'
    }
    return ''
  })()

  $: stepLabel = (() => {
    if (!plan?.steps?.length) return ''
    const total = plan.steps.length
    if (phase === 'result') return `Done (${total} step${total !== 1 ? 's' : ''})`
    return `Step ${stepIndex + 1} of ${total}`
  })()

  function saveHistory() {
    historyStack = [
      ...historyStack,
      {
        stepIndex,
        moveIndex,
        phase,
        candidateSlot,
        currentMag,
        viewCentre: [...viewCentre],
      },
    ]
  }

  function _vrAngSep(p1, p2) {
    const phi1 = (p1[1] * Math.PI) / 180,
      phi2 = (p2[1] * Math.PI) / 180
    const dPhi = ((p2[1] - p1[1]) * Math.PI) / 180
    const dLam = ((p2[0] - p1[0]) * Math.PI) / 180
    const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLam / 2) ** 2
    return (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) * 180) / Math.PI
  }
  function _vrFmt(pos) {
    return `RA=${pos[0].toFixed(3)} Dec=${pos[1].toFixed(3)}`
  }

  function goBack() {
    if (!historyStack.length) return
    const prev = historyStack[historyStack.length - 1]
    historyStack = historyStack.slice(0, -1)
    stepIndex = prev.stepIndex
    moveIndex = prev.moveIndex
    phase = prev.phase
    candidateSlot = prev.candidateSlot
    currentMag = prev.currentMag
    viewCentre = prev.viewCentre
  }

  function enterStep(idx) {
    stepIndex = idx
    const step = plan.steps[idx]
    candidateSlot = 0
    const startPos = _stepStarts[idx] ?? startStar?.pos ?? [0, 0]
    const fovR = fovDeg / 2
    console.log(
      `[VR] enterStep idx=${idx} viewCentre=(${_vrFmt(startPos)}) fovRadius=${fovR.toFixed(3)}° numMoves=${step.moves.length}`,
    )
    step.moves.forEach((m, mi) => {
      const fromDist = _vrAngSep(startPos, m.from.pos)
      const toDist = _vrAngSep(startPos, m.to.pos)
      const ep = [
        startPos[0] + m.multiplier * (m.to.pos[0] - m.from.pos[0]),
        startPos[1] + m.multiplier * (m.to.pos[1] - m.from.pos[1]),
      ]
      console.log(
        `[VR]   move[${mi}] from=(${_vrFmt(m.from.pos)}) fromDist=${fromDist.toFixed(3)}° inFov=${fromDist <= fovR}  to=(${_vrFmt(m.to.pos)}) toDist=${toDist.toFixed(3)}° inFov=${toDist <= fovR}  x${m.multiplier}  endpoint=(${_vrFmt(ep)})`,
      )
    })
    step.candidates.forEach((c, ci) => {
      const d = _vrAngSep(startPos, c.pos)
      console.log(
        `[VR]   candidate[${ci}] id=${c.id} pos=(${_vrFmt(c.pos)}) mag=${getStarMag(c).toFixed(2)} distFromView=${d.toFixed(3)}°`,
      )
    })
    if (step.moves.length === 0) {
      phase = 'test'
      viewCentre = startPos
    } else {
      phase = 'move'
      moveIndex = 0
      viewCentre = startPos
    }
  }

  function handleNext() {
    if (phase !== 'move' || !currentStep) return
    saveHistory()
    const moves = currentStep.moves
    const m = moves[moveIndex]
    const newCentre = [
      viewCentre[0] + m.multiplier * (m.to.pos[0] - m.from.pos[0]),
      viewCentre[1] + m.multiplier * (m.to.pos[1] - m.from.pos[1]),
    ]
    const fovR = fovDeg / 2
    console.log(
      `[VR] handleNext step=${stepIndex} move=${moveIndex} viewWas=(${_vrFmt(viewCentre)}) → newCentre=(${_vrFmt(newCentre)})`,
    )
    if (currentStep.candidates.length >= 2) {
      const c0dist = _vrAngSep(newCentre, currentStep.candidates[0].pos)
      const c1dist = _vrAngSep(newCentre, currentStep.candidates[1].pos)
      console.log(
        `[VR]   after move: c0 dist=${c0dist.toFixed(3)}° inFov=${c0dist <= fovR}  c1 dist=${c1dist.toFixed(3)}° inFov=${c1dist <= fovR}  fovRadius=${fovR.toFixed(3)}°`,
      )
    }
    if (moveIndex < moves.length - 1) {
      moveIndex++
      viewCentre = newCentre
    } else {
      phase = 'test'
      candidateSlot = 0
      viewCentre = newCentre
    }
  }

  function handleYes() {
    if (phase !== 'test' || !currentCandidate) return
    saveHistory()
    currentMag = Math.round(getStarMag(currentCandidate) * 10) / 10
    const nextIdx = stepIndex + 1
    if (nextIdx >= (plan?.steps?.length ?? 0)) {
      phase = 'result'
    } else {
      enterStep(nextIdx)
    }
  }

  function handleNo() {
    if (phase !== 'test') return
    saveHistory()
    if (candidateSlot === 0) {
      candidateSlot = 1
    } else {
      phase = 'result'
    }
  }

  function handleKey(e) {
    if (e.key === 'Escape') dispatch('close')
  }

  async function handleAddToObservation() {
    const today = new Date().toISOString().slice(0, 10)
    try {
      const telName = telescope?.name ?? 'telescope'
      const epName = eyepiece?.name ?? 'eyepiece'
      const starLbl = preferredStarLabel(startStar)
      const constr = startStar?.constellation ? ` (${startStar.constellation})` : ''
      const note = `Visual range (${telName}, ${epName}): mag ${currentMag.toFixed(1)} at ${formatTime(time)} near ${starLbl}${constr}`
      const obs = (await getTodayObservation()) ?? { date: today, objects: [] }
      if (!Array.isArray(obs.objects)) obs.objects = []
      obs.notes = obs.notes ? `${obs.notes}\n${note}` : note
      await putObservation(obs)
      logConfirmMsg = `Added: "${note}"`
      resultLogged = true
    } catch (err) {
      logConfirmMsg = `Error saving: ${err?.message ?? 'unknown error'}`
    }
  }
</script>

<svelte:window on:keydown={handleKey} />

<div class="overlay" on:pointerdown|stopPropagation>
  <div class="header">
    <button class="back-btn" type="button" on:click={() => dispatch('close')}>←</button>
    <span class="header-title">Visual Range</span>
    {#if stepLabel}
      <span class="step-label">{stepLabel}</span>
    {/if}
  </div>

  <div class="body">
    <div class="canvas-wrap">
      <SkyCanvas
        ra0={viewCentre[0]}
        dec0={viewCentre[1]}
        fov={fovDeg}
        {lat}
        {lon}
        {time}
        finderMode={true}
        showDsos={false}
        showSolarSystem={false}
        showConstellationLines={false}
        showConstellationNames={false}
        showConstellationBoundaries={false}
        showFovCircle={false}
        showHorizon={true}
        magLimitOverride={magLimitForView}
        overlayArrows={guideArrows}
        objects={_starObjects}
      />
    </div>

    {#if phase === 'move'}
      {#if instructionText}
        <p class="instruction">{instructionText}</p>
      {/if}
      <div class="actions">
        <button class="btn secondary" disabled={historyStack.length === 0} on:click={goBack}>Previous</button>
        <button class="btn primary" on:click={handleNext}>
          {currentStep && moveIndex < currentStep.moves.length - 1 ? 'Next move' : 'Next'}
        </button>
      </div>
    {:else if phase === 'test'}
      {#if instructionText}
        <p class="instruction">{instructionText}</p>
      {/if}
      {#if currentCandidate && candidateSlot === 1}
        <div class="candidate-info">
          <span class="slot-note">fallback star</span>
        </div>
      {/if}
      <div class="actions">
        <button class="btn secondary" disabled={historyStack.length === 0} on:click={goBack}>Previous</button>
        <button class="btn danger" on:click={handleNo}>No</button>
        <button class="btn primary" on:click={handleYes}>Yes</button>
      </div>
    {:else}
      <div class="result-box">
        <div class="result-mag">{currentMag.toFixed(1)}</div>
        <div class="result-label">limiting magnitude</div>
        {#if logConfirmMsg}
          <p class="log-confirm">{logConfirmMsg}</p>
        {/if}
        <div class="result-actions">
          <button class="btn secondary" disabled={resultLogged} on:click={handleAddToObservation}
            >{resultLogged ? 'Recorded' : 'Add to observation'}</button
          >
          <button class="btn primary" on:click={() => dispatch('close')}>Sky View</button>
        </div>
      </div>
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
    z-index: 13;
    background: #040404;
    color: var(--fg);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .header {
    display: flex;
    align-items: center;
    height: 2.75rem;
    padding: 0 0.75rem;
    border-bottom: 1px solid rgba(200, 0, 0, 0.15);
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .back-btn {
    background: none;
    border: none;
    color: var(--fg);
    font-size: 0.9rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }

  .back-btn:hover {
    background: rgba(200, 0, 0, 0.08);
  }

  .header-title {
    font-size: 1rem;
    font-weight: 600;
  }

  .step-label {
    margin-left: auto;
    font-size: 0.78rem;
    opacity: 0.55;
  }

  .body {
    flex: 1;
    overflow-y: auto;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
  }

  .canvas-wrap {
    width: min(100%, calc(100vh - 16rem));
    aspect-ratio: 1;
    clip-path: circle(50%);
    border-radius: 50%;
    overflow: hidden;
    border: 1px solid rgba(200, 0, 0, 0.2);
    flex-shrink: 0;
  }

  .instruction {
    font-size: 0.88rem;
    text-align: center;
    line-height: 1.4;
    max-width: 26rem;
    margin: 0;
    opacity: 0.9;
  }

  .candidate-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .slot-note {
    font-size: 0.75rem;
    opacity: 0.5;
    font-style: italic;
  }

  .actions {
    display: flex;
    gap: 0.6rem;
    flex-wrap: wrap;
    justify-content: center;
  }

  .btn {
    border: none;
    border-radius: 8px;
    padding: 0.6rem 1.4rem;
    font-size: 0.88rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 120ms;
  }

  .btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .btn.primary {
    background: var(--accent, #cc0000);
    color: #000000;
  }

  .btn.primary:hover:not(:disabled) {
    opacity: 0.85;
  }

  .btn.secondary {
    background: rgba(200, 0, 0, 0.1);
    color: var(--fg);
    border: 1px solid rgba(200, 0, 0, 0.25);
  }

  .btn.secondary:hover:not(:disabled) {
    background: rgba(200, 0, 0, 0.16);
  }

  .btn.danger {
    background: rgba(200, 0, 0, 0.75);
    color: #000000;
  }

  .btn.danger:hover:not(:disabled) {
    background: rgba(200, 0, 0, 0.95);
  }

  .result-box {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.4rem;
    padding: 1.25rem 1rem;
    background: rgba(200, 0, 0, 0.04);
    border: 1px solid rgba(200, 0, 0, 0.15);
    border-radius: 12px;
    width: 100%;
    max-width: 22rem;
  }

  .result-mag {
    font-size: 3rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    color: var(--accent, #cc0000);
  }

  .result-label {
    font-size: 0.75rem;
    opacity: 0.5;
    text-transform: uppercase;
    letter-spacing: 0.07em;
  }

  .log-confirm {
    font-size: 0.76rem;
    opacity: 0.65;
    text-align: center;
    margin: 0.25rem 0 0;
    max-width: 20rem;
  }

  .result-actions {
    display: flex;
    gap: 0.6rem;
    margin-top: 0.5rem;
    flex-wrap: wrap;
    justify-content: center;
  }
</style>
