import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

async function pickFolder(title) {
  const res = await fetch(`/api/pick-folder?title=${encodeURIComponent(title)}`)
  if (!res.ok) return ''
  const data = await res.json()
  return data.path || ''
}

function FolderInput({ label, value, onChange, placeholder, required, title }) {
  const [picking, setPicking] = useState(false)

  async function handleBrowse() {
    setPicking(true)
    try {
      const path = await pickFolder(title)
      if (path) onChange(path)
    } finally {
      setPicking(false)
    }
  }

  return (
    <label className="flex flex-col gap-1">
      <span className="text-muted text-xs">{label}</span>
      <div className="flex gap-1.5">
        <input
          className="flex-1 bg-bg border border-border rounded px-3 py-2 text-txt text-sm font-mono focus:border-accent outline-none"
          placeholder={placeholder}
          value={value}
          onChange={e => onChange(e.target.value)}
          required={required}
        />
        <button
          type="button"
          onClick={handleBrowse}
          disabled={picking}
          className="px-3 py-2 text-xs bg-border text-txt rounded hover:bg-muted/30 transition whitespace-nowrap disabled:opacity-50"
          title="Otevřít průzkumník souborů">
          {picking ? '…' : '📁'}
        </button>
      </div>
    </label>
  )
}

function NewScanModal({ onClose, onStarted }) {
  const [inputDir, setInputDir] = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (!inputDir.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await api.createSession({ input_dir: inputDir.trim(), output_dir: outputDir.trim(), name: name.trim() })
      onStarted(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-surf border border-border rounded-lg p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <h2 className="font-syne text-accent text-lg font-bold mb-4">Nový scan</h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <FolderInput
            label="Složka s fotkami *"
            value={inputDir}
            onChange={v => {
              setInputDir(v)
              setName(v.split('\\').filter(Boolean).pop() || '')
              setOutputDir(v ? v.replace(/\\+$/, '') + '\\_dashboard' : '')
            }}
            placeholder="Z:\Foto\RAW\2025_Serie"
            required
            title="Vyberte složku s fotkami"
          />
          <FolderInput
            label="Výstupní složka (volitelné, default: input/_dashboard)"
            value={outputDir}
            onChange={setOutputDir}
            placeholder="Z:\Foto\RAW\2025_Serie\_dashboard"
            title="Vyberte výstupní složku"
          />
          <label className="flex flex-col gap-1">
            <span className="text-muted text-xs">Název série (volitelné)</span>
            <input
              className="bg-bg border border-border rounded px-3 py-2 text-txt text-sm font-mono focus:border-accent outline-none"
              placeholder="2025_Tatry"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </label>
          {error && <p className="text-bad text-xs">{error}</p>}
          <div className="flex gap-2 mt-2 justify-end">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-xs bg-border text-txt rounded hover:bg-muted/30 transition">
              Zrušit
            </button>
            <button type="submit" disabled={loading}
              className="px-4 py-2 text-xs bg-accent text-black font-bold rounded hover:bg-yellow-400 transition disabled:opacity-50">
              {loading ? 'Spouštím...' : 'Spustit scan'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

const PHASE_LABEL = {
  init:          'Spouštím...',
  loading_model: 'Načítám CLIP model (1–5 min)…',
  scanning:      'Skenování',
  dedup:         'Hledám duplicity',
  saving:        'Ukládám do DB',
}

function JobBanner({ job, onDismiss }) {
  if (!job) return null

  const isRunning = job.status === 'running'
  const isError   = job.status === 'error'
  const isDone    = job.status === 'done'
  const borderColor = isError ? '#c0392b' : isDone ? '#27ae60' : '#3d9eff'
  const textColor   = isError ? '#c0392b' : isDone ? '#27ae60' : '#3d9eff'

  const pct = job.total > 0 ? Math.round(job.current / job.total * 100) : 0
  const phaseLabel = PHASE_LABEL[job.phase] ?? 'Probíhá...'

  return (
    <div className="mb-4 border rounded-lg overflow-hidden text-xs"
         style={{ borderColor }}>
      {/* Progress bar */}
      {isRunning && job.total > 0 && (
        <div className="h-1 bg-border">
          <div className="h-full bg-accent2 transition-all duration-300" style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className="p-3 flex items-center gap-3">
        {isRunning && (
          <span className="inline-block w-3 h-3 border-2 border-accent2 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        )}
        <span style={{ color: textColor }} className="font-semibold">
          {isDone && '✓ Scan dokončen'}
          {isError && `✕ Scan selhal${job.error ? ': ' + job.error : ''}`}
          {isRunning && phaseLabel}
        </span>

        {/* Photo counter */}
        {isRunning && job.total > 0 && (
          <span className="text-txt">
            {job.phase === 'loading_model'
              ? <>{job.total.toLocaleString('cs')} fotek celkem</>
              : <>{job.current.toLocaleString('cs')} / {job.total.toLocaleString('cs')} fotek
                  <span className="text-accent ml-1.5 font-bold">{pct}%</span>
                </>
            }
          </span>
        )}

        <span className="text-muted text-[0.6rem] ml-1">#{job.id}</span>
        {!isRunning && (
          <button onClick={onDismiss} className="ml-auto text-muted hover:text-txt">✕</button>
        )}
      </div>
    </div>
  )
}

export default function SessionList() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [activeJob, setActiveJobRaw] = useState(() => {
    try { return JSON.parse(localStorage.getItem('activeJob')) } catch { return null }
  })

  function setActiveJob(updater) {
    setActiveJobRaw(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      if (next) localStorage.setItem('activeJob', JSON.stringify(next))
      else localStorage.removeItem('activeJob')
      return next
    })
  }

  async function load() {
    try {
      setSessions(await api.getSessions())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // Restore any running job from backend (survives page reload + backend restart)
    if (!activeJob || activeJob.status !== 'running') {
      api.getJobs().then(jobs => {
        const running = Object.entries(jobs)
          .filter(([, j]) => j.status === 'running')
          .sort((a, b) => (b[1].pid ?? 0) - (a[1].pid ?? 0))[0]
        if (running) {
          const [id, job] = running
          setActiveJob({ ...job, id })
        }
      }).catch(() => {})
    }
  }, [])

  // Poll active job
  useEffect(() => {
    if (!activeJob || activeJob.status !== 'running') return
    const timer = setInterval(async () => {
      try {
        const res = await api.getJobStatus(activeJob.id)
        setActiveJob(j => ({ ...j, ...res }))
        if (res.status !== 'running') {
          clearInterval(timer)
          load()
        }
      } catch (e) {
        // Job not found (backend restarted) — dismiss
        setActiveJob(j => ({ ...j, status: 'error', error: 'Backend byl restartován' }))
        clearInterval(timer)
      }
    }, 1000)
    return () => clearInterval(timer)
  }, [activeJob?.id, activeJob?.status])

  async function handleDelete(e, id) {
    e.stopPropagation()
    if (!confirm('Smazat tuto sérii a všechny její fotky z databáze?')) return
    await api.deleteSession(id)
    setSessions(s => s.filter(x => x.id !== id))
  }

  function fmtDate(iso) {
    if (!iso) return '—'
    return new Date(iso).toLocaleString('cs-CZ', { dateStyle: 'short', timeStyle: 'short' })
  }

  return (
    <div className="min-h-screen bg-bg text-txt font-mono">
      <header className="bg-surf border-b border-border px-6 py-4 sticky top-0 z-10 flex items-center gap-4">
        <span className="font-syne text-accent text-xl font-extrabold tracking-tight">PHOTO LIBRARY</span>
        <span className="text-muted text-xs">dashboard</span>
        <button
          onClick={() => setShowModal(true)}
          className="ml-auto bg-accent text-black font-bold text-xs px-4 py-2 rounded hover:bg-yellow-400 transition">
          + Nový scan
        </button>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <JobBanner job={activeJob} onDismiss={() => { setActiveJob(null); localStorage.removeItem('activeJob') }} />

        {loading && <p className="text-muted text-sm">Načítám...</p>}
        {error && <p className="text-bad text-sm">Chyba: {error}</p>}

        {!loading && sessions.length === 0 && (
          <div className="text-center py-16 text-muted">
            <p className="text-lg mb-2">Zatím žádné naskenované složky</p>
            <p className="text-xs">Spusť první scan přes tlačítko „+ Nový scan" nebo pomocí photo_score.py --db</p>
          </div>
        )}

        {sessions.length > 0 && (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="text-left py-2 pr-4">Název</th>
                <th className="text-left py-2 pr-4 hidden sm:table-cell">Složka</th>
                <th className="text-right py-2 pr-4">Fotek</th>
                <th className="text-right py-2 pr-4">Vybráno</th>
                <th className="text-left py-2 pr-4 hidden md:table-cell">Datum scanu</th>
                <th className="py-2 w-8"></th>
              </tr>
            </thead>
            <tbody>
              {sessions.map(s => (
                <tr
                  key={s.id}
                  onClick={() => navigate(`/session/${s.id}`)}
                  className="border-b border-border hover:bg-surf cursor-pointer transition group">
                  <td className="py-3 pr-4">
                    <span className="text-txt font-semibold group-hover:text-accent transition">{s.name}</span>
                  </td>
                  <td className="py-3 pr-4 hidden sm:table-cell">
                    <span className="text-muted text-xs truncate max-w-xs block">{s.input_dir}</span>
                  </td>
                  <td className="py-3 pr-4 text-right text-accent font-bold">{s.total_photos}</td>
                  <td className="py-3 pr-4 text-right">
                    <span className={s.selected_count > 0 ? 'text-good font-bold' : 'text-muted'}>
                      {s.selected_count ?? 0}
                    </span>
                  </td>
                  <td className="py-3 pr-4 hidden md:table-cell text-muted text-xs">{fmtDate(s.scanned_at)}</td>
                  <td className="py-3">
                    <button
                      onClick={e => handleDelete(e, s.id)}
                      className="text-muted hover:text-bad transition text-xs opacity-0 group-hover:opacity-100">
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>

      {showModal && (
        <NewScanModal
          onClose={() => setShowModal(false)}
          onStarted={job => {
            setShowModal(false)
            setActiveJob({ ...job, id: job.job_id })
          }}
        />
      )}
    </div>
  )
}
