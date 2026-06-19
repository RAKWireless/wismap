import { useState, useEffect, useRef, useMemo } from 'react'
import { fetchBases, fetchBase, fetchCores, fetchModules, validate, solve } from '../api'
import FunctionTable from './FunctionTable'

export default function CombineTool({ initialConfig, onConfigConsumed }) {
  const [bases, setBases] = useState([])
  const [cores, setCores] = useState([])
  const [allModules, setAllModules] = useState([])
  const [selectedBase, setSelectedBase] = useState('')
  const [baseInfo, setBaseInfo] = useState(null)
  const [assignments, setAssignments] = useState({}) // { SLOT_NAME: 'RAK4631' }
  const [blocked, setBlocked] = useState(new Set())
  const [result, setResult] = useState(null)
  const pendingConfig = useRef(null)
  // Monotonic id so a slow validate() response from a previous base can't
  // overwrite the cleared state.
  const validateReqId = useRef(0)
  // Solve (slot-placement) chooser state.
  const [solutions, setSolutions] = useState(null)   // /solve response, or null
  const [solving, setSolving] = useState(false)
  const [solveError, setSolveError] = useState(null)
  const [expandedRank, setExpandedRank] = useState(1)
  const solveReqId = useRef(0)

  // Initial: load the catalog once.
  useEffect(() => {
    fetchBases().then(setBases)
    fetchCores().then(setCores)
    fetchModules().then(setAllModules)
  }, [])

  // Apply a pending #combine/... config once the base is known.
  useEffect(() => {
    if (!initialConfig) return
    pendingConfig.current = initialConfig
    setSelectedBase(initialConfig.base.toUpperCase())
    onConfigConsumed()
  }, [initialConfig, onConfigConsumed])

  // When base changes, clear every derived bit of state before fetching the
  // new base — otherwise the validate effect can fire with the previous base's
  // assignments while the new baseInfo is loading.
  useEffect(() => {
    setBaseInfo(null)
    setResult(null)
    setAssignments({})
    setBlocked(new Set())
    setSolutions(null)
    setSolveError(null)
    if (!selectedBase) return
    fetchBase(selectedBase).then(setBaseInfo)
  }, [selectedBase])

  // Build per-slot eligibility from compatible_slots / cores list.
  // For SENSOR/IO/POWER slots: modules whose compatible_slots[base][] includes this slot.
  // For CORE slot: all Cores (the base has a CORE slot by definition for cores to apply).
  const eligibleBySlot = useMemo(() => {
    if (!baseInfo) return {}
    const out = {}
    const slotInfo = baseInfo.slot_info || {}
    for (const slotName of baseInfo.slots) {
      const accepts = slotInfo[slotName]?.accepts_type
      if (accepts === 'WisCore') {
        out[slotName] = cores
      } else {
        out[slotName] = allModules.filter(m => {
          const slots = (m.compatible_slots || {})[baseInfo.id] || []
          return slots.includes(slotName)
        })
      }
    }
    return out
  }, [baseInfo, cores, allModules])

  // Once baseInfo + eligibility are ready, apply any pending #combine config
  // OR reset to empty assignments.
  useEffect(() => {
    if (!baseInfo) return
    const slotNames = baseInfo.slots
    const config = pendingConfig.current
    if (config && config.base.toUpperCase() === baseInfo.id && config.modules.length > 0) {
      pendingConfig.current = null
      const next = {}
      for (let i = 0; i < slotNames.length; i++) {
        const slotName = slotNames[i]
        const moduleId = i < config.modules.length ? config.modules[i] : ''
        next[slotName] = (moduleId && moduleId.toLowerCase() !== 'empty')
          ? moduleId.toUpperCase()
          : ''
      }
      const blockedSet = computeBlocked(next, baseInfo, allModules)
      for (const b of blockedSet) next[b] = ''
      setAssignments(next)
      setBlocked(blockedSet)
    } else {
      const init = {}
      for (const name of slotNames) init[name] = ''
      setAssignments(init)
      setBlocked(new Set())
    }
  }, [baseInfo, allModules])

  const handleAssignment = (slotName, moduleId) => {
    const next = { ...assignments, [slotName]: moduleId }
    const blockedSet = computeBlocked(next, baseInfo, allModules)
    for (const b of blockedSet) next[b] = ''
    setAssignments(next)
    setBlocked(blockedSet)
    setSolutions(null)        // a manual edit invalidates any pending proposal
    setSolveError(null)
  }

  // Auto-validate whenever assignments change.
  useEffect(() => {
    // Bail (and clear) while the user is mid-switch: selectedBase has updated
    // but the corresponding baseInfo hasn't loaded yet. Without this, the
    // effect fires once before our `selectedBase` cleanup commits and would
    // launch a stale validate against the previous base.
    if (!baseInfo || !selectedBase || baseInfo.id !== selectedBase) {
      setResult(null)
      return
    }
    const slotInfo = baseInfo.slot_info || {}
    const baseHasCoreSlot = baseInfo.slots.includes('CORE')
    // Find the Core (CORE slot assignment) and pass it at top-level per §3.5.
    let coreId = null
    const slots = []
    for (const [slotName, moduleId] of Object.entries(assignments)) {
      if (!moduleId) continue
      if (slotInfo[slotName]?.accepts_type === 'WisCore') {
        coreId = moduleId
        continue
      }
      slots.push({ slot: slotName, module: moduleId })
    }
    // For bases with a CORE slot we need the user to pick a Core before we can
    // resolve MCU pins. For coreless bases (RAK6421 Pi Hat) the host platform
    // plays that role, so we validate without a Core.
    if (baseHasCoreSlot && !coreId) {
      setResult(null)
      return
    }
    // Tag the request; only apply its result if it's still the most recent one.
    const reqId = ++validateReqId.current
    validate({ core: coreId, base: baseInfo.id, slots }).then(res => {
      if (reqId === validateReqId.current) setResult(res)
    })
  }, [baseInfo, selectedBase, assignments, blocked])

  // --- Solve (slot placement) ---------------------------------------------
  // Split current assignments into the Core + the non-CORE modules, the same
  // rule the auto-validate effect uses.
  const splitAssignments = () => {
    const slotInfo = (baseInfo && baseInfo.slot_info) || {}
    let coreId = null
    const modules = []
    for (const [slotName, moduleId] of Object.entries(assignments)) {
      if (!moduleId) continue
      if (slotInfo[slotName]?.accepts_type === 'WisCore') coreId = moduleId
      else modules.push(moduleId)
    }
    return { coreId, modules }
  }

  const baseHasCoreSlot = !!(baseInfo && baseInfo.slots.includes('CORE'))
  const { coreId: solveCore, modules: solveModules } =
    baseInfo ? splitAssignments() : { coreId: null, modules: [] }

  let solveDisabledReason = ''
  if (!baseInfo) solveDisabledReason = 'Select a base board first.'
  else if (baseHasCoreSlot && !solveCore) solveDisabledReason = 'Choose a Core module first.'
  else if (solveModules.length === 0) solveDisabledReason = 'Add at least one module to place.'
  const canSolve = !solveDisabledReason && !solving

  const handleSolve = () => {
    if (!canSolve) return
    setSolving(true)
    setSolveError(null)
    const reqId = ++solveReqId.current
    solve({ core: solveCore, base: baseInfo.id, modules: solveModules, max_solutions: 3 })
      .then(res => {
        if (reqId !== solveReqId.current) return
        if (res && res.error) {
          setSolveError(res.error.message || 'Solve failed.')
          setSolutions(null)
        } else {
          setSolutions(res)
          setExpandedRank(1)
        }
      })
      .catch(() => { if (reqId === solveReqId.current) setSolveError('Solve request failed.') })
      .finally(() => { if (reqId === solveReqId.current) setSolving(false) })
  }

  // Apply a chosen solution: rebuild assignments from its slots, keeping the
  // user's Core, then let the existing auto-validate refresh the result table.
  // Reuses the same assignment + computeBlocked path as the #combine deep-link.
  const applySolution = (sol) => {
    const slotInfo = baseInfo.slot_info || {}
    const next = {}
    for (const name of baseInfo.slots) {
      next[name] = (slotInfo[name]?.accepts_type === 'WisCore' && assignments[name])
        ? assignments[name]   // keep the chosen Core
        : ''
    }
    for (const { slot, module } of sol.slots) next[slot] = module
    const blockedSet = computeBlocked(next, baseInfo, allModules)
    for (const b of blockedSet) next[b] = ''
    setAssignments(next)
    setBlocked(blockedSet)
    setSolutions(null)
    setSolveError(null)
  }

  return (
    <div>
      <div className="combine-layout">
        <div className="slot-panel">
          <label>
            Base Board
            <select value={selectedBase} onChange={e => setSelectedBase(e.target.value)}>
              <option value="">-- Select base --</option>
              {bases.map(b => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </label>

          {baseInfo && baseInfo.slots.map(slotName => {
            const slotInfo = (baseInfo.slot_info || {})[slotName] || {}
            const isBlocked = blocked.has(slotName)
            const eligible = eligibleBySlot[slotName] || []
            return (
              <label key={slotName}>
                {slotName}
                {slotInfo.double && ' (double)'}
                {isBlocked && ' - BLOCKED'}
                <select
                  value={isBlocked ? '' : (assignments[slotName] || '')}
                  onChange={e => handleAssignment(slotName, e.target.value)}
                  disabled={isBlocked}
                >
                  <option value="">Empty</option>
                  {eligible.map(m => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
              </label>
            )
          })}

          {baseInfo && (
            <button
              type="button"
              className="solve-btn"
              onClick={handleSolve}
              disabled={!canSolve}
              title={solveDisabledReason || 'Suggest slot placements for the selected modules'}
            >
              {solving ? 'Solving…' : 'Solve'}
            </button>
          )}

          {solveError && <div className="solve-error">{solveError}</div>}

          {solutions && (
            <div className="solve-results">
              <div className="solve-results-head">
                <span>{solutions.solution_count} solution{solutions.solution_count === 1 ? '' : 's'}</span>
                <button
                  type="button"
                  className="solve-dismiss"
                  onClick={() => setSolutions(null)}
                  title="Keep current layout"
                >✕</button>
              </div>
              {solutions.truncated && (
                <div className="solve-note">Best effort — search space capped.</div>
              )}
              {solutions.solution_count === 0 && (
                <div className="solve-note">No modules could be placed.</div>
              )}
              {solutions.solutions.map(sol => {
                const open = expandedRank === sol.rank
                const status = sol.error_count
                  ? { cls: 'err', label: `✗${sol.error_count}` }
                  : sol.warning_count
                    ? { cls: 'warn', label: `⚠${sol.warning_count}` }
                    : { cls: 'ok', label: '✓' }
                return (
                  <div key={sol.rank} className={`solve-option${sol.rank === 1 ? ' best' : ''}`}>
                    <button
                      type="button"
                      className="solve-summary"
                      aria-expanded={open}
                      onClick={() => setExpandedRank(open ? -1 : sol.rank)}
                    >
                      <span className="solve-rank">{sol.rank === 1 ? '★ 1' : sol.rank}</span>
                      <span className={`solve-status ${status.cls}`}>{status.label}</span>
                      <span className="solve-top" title="sensors on the top layer">▲{sol.sensors_on_top}</span>
                      <span className="solve-count">{sol.slots.length} slot{sol.slots.length === 1 ? '' : 's'}</span>
                      {sol.unplaced.length > 0 && (
                        <span className="solve-unplaced-count" title="unplaced modules">·{sol.unplaced.length}✗</span>
                      )}
                      <span className="solve-chevron">{open ? '▾' : '▸'}</span>
                    </button>
                    {open && (
                      <div className="solve-detail">
                        <div className="solve-placement">
                          {sol.slots.map(s => (
                            <div key={s.slot} className="solve-place-row">
                              <span className="solve-slot">{s.slot}</span>
                              <span className="solve-mod">{s.module}</span>
                            </div>
                          ))}
                        </div>
                        {sol.conflicts.map((c, i) => (
                          <div key={`e${i}`} className="solve-reason err">✗ {c.message}</div>
                        ))}
                        {sol.warnings.map((w, i) => (
                          <div key={`w${i}`} className="solve-reason warn">⚠ {w.message}</div>
                        ))}
                        {sol.unplaced.map((u, i) => (
                          <div key={`u${i}`} className="solve-reason unplaced">
                            ! {u.module} — {unplacedReason(u.reason)}
                          </div>
                        ))}
                        <button
                          type="button"
                          className="solve-apply"
                          onClick={() => applySolution(sol)}
                        >Use this layout</button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

        </div>

        <div>
          {result && <FunctionTable result={result} />}
        </div>
      </div>
    </div>
  )
}

/**
 * Recompute which slots are blocked by a double-sized sensor occupying its sibling.
 * A double sensor placed in a slot with `double_blocks` set forces the named
 * adjacent slot to BLOCKED.
 */
function computeBlocked(assignments, baseInfo, allModules) {
  const blockedSet = new Set()
  if (!baseInfo) return blockedSet
  const slotInfo = baseInfo.slot_info || {}
  const moduleById = Object.fromEntries(allModules.map(m => [m.id, m]))
  for (const [slotName, info] of Object.entries(slotInfo)) {
    if (!info.double_blocks) continue
    const mid = assignments[slotName]
    if (!mid) continue
    const mod = moduleById[mid]
    if (mod && mod.double) {
      blockedSet.add(info.double_blocks)
    }
  }
  return blockedSet
}

/** Friendly text for a /solve `unplaced[].reason` code. */
function unplacedReason(code) {
  switch (code) {
    case 'unknown_module': return 'not in the WisMAP catalog'
    case 'incompatible_with_base': return 'no compatible slot on this base'
    case 'no_free_slot': return 'no free slot left'
    default: return code
  }
}
