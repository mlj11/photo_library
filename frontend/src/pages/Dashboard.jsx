import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../api'
import PhotoCard from '../components/PhotoCard'
import FilterBar from '../components/FilterBar'
import GroupNav from '../components/GroupNav'
import SelectionBar from '../components/SelectionBar'

const DEFAULT_FILTERS = {
  sort: 'name',
  order: 'asc',
  category: 'all',
  group_id: -2,
  special: 'all',
  min_score: null,
  search: '',
}

export default function Dashboard() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [session, setSession] = useState(null)
  const [photos, setPhotos] = useState([])
  const [stats, setStats] = useState(null)
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [cardSize, setCardSize] = useState(200)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notification, setNotification] = useState('')
  const [allSessions, setAllSessions] = useState([])
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const switcherRef = useRef(null)

  const notifTimer = useRef(null)

  function notify(msg) {
    setNotification(msg)
    clearTimeout(notifTimer.current)
    notifTimer.current = setTimeout(() => setNotification(''), 3000)
  }

  // Close switcher on outside click
  useEffect(() => {
    function onClickOutside(e) {
      if (switcherRef.current && !switcherRef.current.contains(e.target))
        setSwitcherOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  // Initial load
  useEffect(() => {
    Promise.all([api.getSession(id), api.getStats(id), api.getSessions()])
      .then(([s, st, all]) => {
        setSession(s)
        setStats(st)
        setAllSessions(all)
      })
      .catch(e => setError(e.message))
  }, [id])

  // Fetch photos on filter change
  useEffect(() => {
    const params = {
      sort: filters.sort,
      order: filters.order,
      category: filters.category !== 'all' ? filters.category : undefined,
      group_id: filters.group_id !== -2 ? filters.group_id : undefined,
      special: filters.special !== 'all' ? filters.special : undefined,
      min_score: filters.min_score ?? undefined,
      search: filters.search || undefined,
    }
    api.getPhotos(id, params)
      .then(p => { setPhotos(p); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [id, filters])

  // Card size CSS var
  useEffect(() => {
    document.documentElement.style.setProperty('--card-size', `${cardSize}px`)
  }, [cardSize])

  const handleUpdate = useCallback(async (photoId, updates) => {
    setPhotos(prev => prev.map(p => p.id === photoId ? { ...p, ...updates } : p))
    try {
      await api.updatePhoto(photoId, updates)
    } catch (e) {
      notify(`Chyba: ${e.message}`)
    }
  }, [])

  const handleToggleSelect = useCallback((photoId, checked) => {
    handleUpdate(photoId, { selected: checked })
  }, [handleUpdate])

  const handleOpenFile = useCallback(async (path) => {
    try {
      await api.openFile(path)
    } catch {
      notify('[!] Nelze otevřít soubor – backend musí běžet')
    }
  }, [])

  const selectedPhotos = photos.filter(p => p.selected)

  function handleSelectVisible() {
    const ids = photos.map(p => p.id)
    ids.forEach(id => handleUpdate(id, { selected: true }))
  }

  function handleClearSelection() {
    photos.filter(p => p.selected).forEach(p => handleUpdate(p.id, { selected: false }))
  }

  const scoreMin = stats?.score_min ?? 0
  const scoreMax = stats?.score_max ?? 1

  if (error) return (
    <div className="min-h-screen bg-bg flex items-center justify-center text-bad text-sm">
      {error} <Link to="/" className="ml-4 text-accent underline">← Zpět</Link>
    </div>
  )

  return (
    <div className="min-h-screen bg-bg text-txt font-mono">
      {/* Header */}
      <header className="bg-surf border-b border-border px-4 py-3 sticky top-0 z-20 flex items-center gap-3 flex-wrap">
        <Link to="/" className="text-muted hover:text-accent text-xs transition">← seznam</Link>

        {/* Session switcher */}
        <div ref={switcherRef} className="relative">
          <button
            onClick={() => setSwitcherOpen(v => !v)}
            className="flex items-center gap-1.5 font-syne text-accent font-extrabold text-base hover:text-yellow-400 transition">
            {session?.name ?? '…'}
            {allSessions.length > 1 && (
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" className="mt-0.5 opacity-60">
                <path d="M2 3.5l3 3 3-3"/>
              </svg>
            )}
          </button>

          {switcherOpen && allSessions.length > 1 && (
            <div className="absolute top-full left-0 mt-1 bg-surf border border-border rounded-lg shadow-2xl z-50 min-w-64 max-h-80 overflow-y-auto">
              {allSessions.map(s => (
                <button
                  key={s.id}
                  onClick={() => { navigate(`/session/${s.id}`); setSwitcherOpen(false) }}
                  className={`w-full text-left px-3 py-2.5 flex items-center justify-between gap-3 hover:bg-border/50 transition
                    ${s.id === parseInt(id) ? 'bg-accent/10 text-accent' : 'text-txt'}`}>
                  <div className="flex flex-col gap-0.5 min-w-0">
                    <span className="font-semibold text-xs truncate">{s.name}</span>
                    <span className="text-muted text-[0.6rem] truncate">{s.input_dir}</span>
                  </div>
                  <div className="flex flex-col items-end flex-shrink-0 text-[0.6rem] text-muted">
                    <span>{s.total_photos} fotek</span>
                    {s.selected_count > 0 && <span className="text-accent">{s.selected_count} vyb.</span>}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {session && (
          <span className="text-muted text-xs hidden sm:block">{session.input_dir}</span>
        )}
        <div className="ml-auto flex items-center gap-3 text-xs text-muted">
          {stats && (
            <>
              <span>fotek: <strong className="text-txt">{stats.total}</strong></span>
              <span>vyb: <strong className="text-accent">{stats.selected}</strong></span>
              <span>sk: <strong className="text-txt">{stats.groups}</strong></span>
            </>
          )}
        </div>
      </header>

      {/* Group nav */}
      {stats?.groups > 0 && (
        <div className="bg-surf border-b border-border px-4 py-2">
          <GroupNav
            groupCounts={stats.group_counts ?? {}}
            activeGroupId={filters.group_id}
            onGroupChange={gid => setFilters(f => ({ ...f, group_id: gid }))}
          />
        </div>
      )}

      {/* Filter bar */}
      <FilterBar
        filters={filters}
        stats={stats}
        visibleCount={photos.length}
        onFiltersChange={setFilters}
        cardSize={cardSize}
        onCardSizeChange={setCardSize}
      />

      {/* Photo grid */}
      {loading ? (
        <div className="flex items-center justify-center py-24 text-muted text-sm">Načítám...</div>
      ) : photos.length === 0 ? (
        <div className="flex items-center justify-center py-24 text-muted text-sm">Žádné fotky pro tyto filtry</div>
      ) : (
        <div className="photo-grid pb-20">
          {photos.map(photo => (
            <PhotoCard
              key={photo.id}
              photo={photo}
              scoreMin={scoreMin}
              scoreMax={scoreMax}
              onToggleSelect={handleToggleSelect}
              onOpenFile={handleOpenFile}
              onUpdate={handleUpdate}
            />
          ))}
        </div>
      )}

      {/* Selection bar */}
      <SelectionBar
        selectedPhotos={selectedPhotos}
        allPhotos={photos}
        sessionId={id}
        onClear={handleClearSelection}
        onSelectVisible={handleSelectVisible}
      />

      {/* Notification toast */}
      {notification && (
        <div className="fixed bottom-20 right-4 bg-surf border border-accent rounded px-4 py-2 text-xs text-accent z-50 shadow-lg">
          {notification}
        </div>
      )}
    </div>
  )
}
