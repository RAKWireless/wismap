import { useState, useEffect } from 'react'
import './App.css'
import ModuleList from './components/ModuleList'
import ModuleDetail from './components/ModuleDetail'
import CombineTool from './components/CombineTool'

import { decodeCombineId } from './utils/combineId'

function parseHash(hash) {
  // #c/<v><tokens> — versioned fixed-width hex combine id
  if (hash.startsWith('#c/')) {
    return decodeCombineId(hash)
  }
  // #module/<id>
  if (hash.startsWith('#module/')) {
    const id = hash.slice('#module/'.length)
    if (!id) return null
    return { type: 'module', id }
  }
  return null
}

function App() {
  const [view, setView] = useState('combine') // 'modules' | 'combine'
  const [selectedModule, setSelectedModule] = useState(null)
  const [initialConfig, setInitialConfig] = useState(null)
  const [resetKey, setResetKey] = useState(0)
  const [typeFilter, setTypeFilter] = useState('All')
  const [search, setSearch] = useState('')

  useEffect(() => {
    const apply = () => {
      const parsed = parseHash(window.location.hash)
      if (parsed && parsed.type === 'combine') {
        setInitialConfig(parsed)
        setView('combine')
        setSelectedModule(null)
      } else if (parsed && parsed.type === 'module') {
        setSelectedModule(parsed.id)
        setView('modules')
        setInitialConfig(null)
      }
    }
    apply()
    window.addEventListener('hashchange', apply)
    return () => window.removeEventListener('hashchange', apply)
  }, [])

  return (
    <div className="app">
      <header>
        <h1 style={{ cursor: 'pointer' }} onClick={() => { setResetKey(k => k + 1); setSelectedModule(null); setTypeFilter('All'); setSearch('') }}>
          WisMAP <span style={{ fontSize: '0.5em', fontWeight: 'normal', opacity: 0.7 }}>RAKwireless WisBlock PIN Mapper</span>
        </h1>
        <nav>
          <button
            className={view === 'combine' ? 'active' : ''}
            onClick={() => setView('combine')}
          >
            Combine
          </button>
          <button
            className={view === 'modules' ? 'active' : ''}
            onClick={() => setView('modules')}
          >
            Modules
          </button>
        </nav>
      </header>

      <div key={'modules-' + resetKey} style={{ display: view === 'modules' ? undefined : 'none' }}>
        {!selectedModule && (
          <ModuleList
            onSelect={setSelectedModule}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
            search={search}
            onSearchChange={setSearch}
          />
        )}
        {selectedModule && (
          <ModuleDetail
            moduleId={selectedModule}
            onBack={() => setSelectedModule(null)}
            onSelect={setSelectedModule}
            onTagClick={(tag) => {
              setSearch(tag)
              setSelectedModule(null)
              setView('modules')
            }}
          />
        )}
      </div>
      <div key={'combine-' + resetKey} style={{ display: view === 'combine' ? undefined : 'none' }}>
        <CombineTool
          initialConfig={initialConfig}
          onConfigConsumed={() => setInitialConfig(null)}
        />
      </div>

      <footer>
        <div>WisMAP {__APP_VERSION__}</div>
        <div>Copyright &copy; 2026 RAKwireless Technology Limited. All rights reserved.</div>
      </footer>
    </div>
  )
}

export default App
