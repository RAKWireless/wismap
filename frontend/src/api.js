const BASE = '/api/v1'

function qs(params) {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== '' && v !== 'All')
  if (entries.length === 0) return ''
  return '?' + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')
}

async function getJson(url) {
  const res = await fetch(url)
  if (!res.ok) {
    if (res.status === 404) return null
    throw new Error(`${res.status} ${res.statusText}: ${url}`)
  }
  return res.json()
}

// ───── Cores ─────

export async function fetchCores() {
  const data = await getJson(`${BASE}/cores`)
  return data ? data.cores : []
}

export async function fetchCore(id) {
  return getJson(`${BASE}/cores/${encodeURIComponent(id)}`)
}

// ───── Bases ─────

export async function fetchBases() {
  const data = await getJson(`${BASE}/bases`)
  return data ? data.bases : []
}

export async function fetchBase(id) {
  return getJson(`${BASE}/bases/${encodeURIComponent(id)}`)
}

// ───── Modules ─────

export async function fetchModules(filters) {
  // filters: { type, category, interface, compatible_with_core }
  const data = await getJson(`${BASE}/modules${qs(filters)}`)
  return data ? data.modules : []
}

export async function fetchModule(id, showNc = false) {
  const q = showNc ? '?show_nc=true' : ''
  return getJson(`${BASE}/modules/${encodeURIComponent(id)}${q}`)
}

// ───── Validate ─────

export async function validate({ core, base, slots, options }) {
  const res = await fetch(`${BASE}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ core, base, slots, options }),
  })
  return res.json()
}

// ───── Solve (slot placement) ─────

export async function solve({ core, base, modules, max_solutions, options }) {
  const res = await fetch(`${BASE}/solve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ core, base, modules, max_solutions, options }),
  })
  return res.json()
}

// ───── Unified browse / detail helpers ─────

/**
 * Fetch the merged catalog (cores + bases + modules) for the unified browse view.
 * Each item carries its `type` so callers can dispatch detail lookups.
 */
export async function fetchAllItems() {
  const [cores, bases, modules] = await Promise.all([
    fetchCores(), fetchBases(), fetchModules(),
  ])
  return [...cores, ...bases, ...modules]
}

/**
 * Type-aware detail fetch. Tries modules first (the largest set), then
 * cores, then bases. Returns the first hit plus its `_endpoint` ("module"
 * | "core" | "base") so callers can render the right view.
 */
export async function fetchItem(id, showNc = false) {
  const mod = await fetchModule(id, showNc)
  if (mod) return { ...mod, _endpoint: 'module' }
  const core = await fetchCore(id)
  if (core) return { ...core, _endpoint: 'core' }
  const base = await fetchBase(id)
  if (base) return { ...base, _endpoint: 'base' }
  return null
}
