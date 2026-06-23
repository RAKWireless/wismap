import { useState } from 'react'
import { exportMarkdown, exportPdf } from '../utils/exportCombine'
import { encodeCombineId } from '../utils/combineId'

export default function FunctionTable({ result }) {
  const [copied, setCopied] = useState(false)

  if (!result) return null

  const {
    columns, slot_module, function_table,
    conflicts = [], warnings = [],
    highlighted_functions = [],
    documentation = [], notes = [],
  } = result
  const conflictFns = new Set(highlighted_functions)

  // Build module id -> documentation URL lookup from the documentation strings.
  const docUrls = {}
  for (const d of documentation) {
    const idx = d.lastIndexOf(': http')
    if (idx !== -1) {
      const url = d.slice(idx + 2)
      for (const modId of Object.values(slot_module)) {
        if (modId !== 'EMPTY' && modId !== 'BLOCKED'
            && d.toLowerCase().startsWith(modId.toLowerCase())) {
          docUrls[modId] = url
        }
      }
    }
  }

  const buildShareUrl = () => {
    const entries = Object.entries(slot_module)
    const baseEntry = entries.find(([key]) => key === 'BASE')
    if (!baseEntry) return null
    const modules = entries.filter(([key]) => key !== 'BASE').map(([, v]) => v)
    return encodeCombineId(baseEntry[1], modules)
  }

  const handleCopyLink = (e) => {
    e.preventDefault()
    const hash = buildShareUrl()
    if (!hash) return
    window.location.hash = hash
    const url = window.location.href
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  // Merge structured conflicts + warnings into a single notes display, then
  // append free-text legacy notes.
  const allConflictNotes = [
    ...conflicts.map(c => ({ severity: 'error', text: c.message })),
    ...warnings.map(w => ({ severity: 'warning', text: w.message })),
  ]

  return (
    <div>
      <div className="function-table-wrap">
        <table className="function-table">
          <thead>
            <tr>{columns.map(c => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            <tr className="module-row">
              <td>MODULE</td>
              {Object.values(slot_module).map((v, i) => (
                <td key={i}>
                  {docUrls[v]
                    ? <a href={docUrls[v]} target="_blank" rel="noreferrer">{v}</a>
                    : v
                  }
                </td>
              ))}
            </tr>
            {Object.entries(function_table).map(([fn, row]) => (
              <tr key={fn} className={
                conflictFns.has(fn) ? 'conflict'
                : fn === 'I2C_ADDR' ? 'i2c-addr-row'
                : ''
              }>
                {row.map((cell, i) => <td key={i}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(allConflictNotes.length > 0 || notes.length > 0) && (
        <div className="notes">
          <h3>Notes</h3>
          <ul>
            {allConflictNotes.map((n, i) => (
              <li key={'c' + i} className={n.severity === 'error' ? 'conflict-note' : 'warning-note'}>{n.text}</li>
            ))}
            {notes.map((n, i) => <li key={'n' + i}>{n}</li>)}
          </ul>
        </div>
      )}

      {documentation.length > 0 && (
        <div className="docs">
          <h3>Documentation</h3>
          <ul>
            {documentation.map((d, i) => {
              const idx = d.lastIndexOf(': http')
              if (idx === -1) return <li key={i}>{d}</li>
              const label = d.slice(0, idx)
              const url = d.slice(idx + 2)
              return (
                <li key={i}>
                  {label}: <a href={url} target="_blank" rel="noreferrer">{url}</a>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      <div className="docs">
        <h3>Actions</h3>
        <ul>
          <li>
            <a href={buildShareUrl()} onClick={handleCopyLink}>
              {copied ? 'Copied!' : 'Copy link to this analysis'}
            </a>
          </li>
          <li><a href="#" onClick={e => { e.preventDefault(); const hash = buildShareUrl(); const url = hash ? `${window.location.origin}${window.location.pathname}${hash}` : null; exportMarkdown(result, url) }}>Export as Markdown</a></li>
          <li><a href="#" onClick={e => { e.preventDefault(); const hash = buildShareUrl(); const url = hash ? `${window.location.origin}${window.location.pathname}${hash}` : null; exportPdf(result, url) }}>Export as PDF</a></li>
        </ul>
      </div>
    </div>
  )
}
