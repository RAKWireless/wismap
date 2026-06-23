export const COMBINE_HASH_PREFIX = '#c/'
export const COMBINE_ID_VERSION = '1'

const FIELD_WIDTH = 4
const CODE_TO_ID = { 5005: 'rak5005-o' }

function toCode(id) {
  const m = id.match(/^rak(\d+)/i)
  return m ? Number(m[1]) : null
}

function toHex(n) {
  return n.toString(16).padStart(FIELD_WIDTH, '0')
}

function fromCode(n) {
  return CODE_TO_ID[n] ?? ('rak' + n)
}

export function encodeCombineId(base, modules) {
  if (!base) return null
  const baseCode = toCode(base)
  if (baseCode === null) return null
  const tokens = [toHex(baseCode)]
  for (const m of modules) {
    if (!m || m.toUpperCase() === 'EMPTY' || m.toUpperCase() === 'BLOCKED') {
      tokens.push('0000')
    } else {
      const code = toCode(m)
      tokens.push(code !== null ? toHex(code) : '0000')
    }
  }
  while (tokens.length > 1 && tokens[tokens.length - 1] === '0000') tokens.pop()
  return COMBINE_HASH_PREFIX + COMBINE_ID_VERSION + tokens.join('')
}

function decodeV1(body) {
  if (body.length === 0 || body.length % FIELD_WIDTH !== 0) return null
  const groups = []
  for (let i = 0; i < body.length; i += FIELD_WIDTH) groups.push(body.slice(i, i + FIELD_WIDTH))
  const baseCode = parseInt(groups[0], 16)
  if (!baseCode || isNaN(baseCode)) return null
  const base = fromCode(baseCode)
  const modules = groups.slice(1).map(g => {
    const n = parseInt(g, 16)
    return (!n || isNaN(n)) ? '' : fromCode(n)
  })
  return { type: 'combine', base, modules }
}

const DECODERS = { '1': decodeV1 }

export function decodeCombineId(hash) {
  if (!hash.startsWith(COMBINE_HASH_PREFIX)) return null
  const payload = hash.slice(COMBINE_HASH_PREFIX.length)
  if (!payload) return null
  const decoder = DECODERS[payload[0]]
  if (!decoder) return null
  return decoder(payload.slice(1))
}
