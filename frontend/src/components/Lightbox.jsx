import { useEffect, useRef, useState } from 'react'

const CAT_LABEL = {
  portret_blizky: 'portret-B', portret_vzdaleny: 'portret-V',
  krajina: 'krajina', detail: 'detail', akce: 'akce', scena: 'scena',
}

function previewUrl(photo) {
  return `/api/preview?path=${encodeURIComponent(photo.path)}`
}

export default function Lightbox({ photos, index, onClose, onNavigate, onOpenFile }) {
  const photo = photos[index]
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(false)
  const prevIdx = useRef(index)

  // Reset loading state when photo changes
  useEffect(() => {
    if (prevIdx.current !== index) {
      setLoading(true)
      setError(false)
      prevIdx.current = index
    }
  }, [index])

  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft'  && index > 0)                  onNavigate(index - 1)
      else if (e.key === 'ArrowRight' && index < photos.length - 1)  onNavigate(index + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, photos.length, onClose, onNavigate])

  if (!photo) return null

  const cat = CAT_LABEL[photo.user_category || photo.category] || photo.category

  return (
    <div
      className="fixed inset-0 z-50 bg-black/95 flex flex-col"
      onClick={onClose}>

      {/* Top bar */}
      <div
        className="flex items-center gap-3 px-4 py-2.5 bg-black/70 border-b border-white/10 flex-shrink-0"
        onClick={e => e.stopPropagation()}>
        <span className="text-txt font-mono text-xs truncate max-w-xs">{photo.name}</span>
        <span className="text-accent font-bold text-xs">{photo.score?.toFixed(4)}</span>
        <span className="text-accent2 text-[0.6rem] px-1.5 py-0.5 border border-accent2/30 rounded">{cat}</span>
        {photo.dof && <span className="text-purple-400 text-[0.6rem]">BOKEH</span>}
        <span className="text-muted text-[0.6rem] ml-1">{index + 1} / {photos.length}</span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => onOpenFile(photo.path)}
            className="text-[0.65rem] px-3 py-1 border border-border text-muted rounded hover:border-accent hover:text-accent transition">
            Otevřít v aplikaci
          </button>
          <button onClick={onClose} className="text-muted hover:text-txt text-lg leading-none px-1">✕</button>
        </div>
      </div>

      {/* Image area */}
      <div className="flex-1 flex items-center justify-center relative min-h-0">

        {/* Left arrow */}
        {index > 0 && (
          <button
            onClick={e => { e.stopPropagation(); onNavigate(index - 1) }}
            className="absolute left-3 z-10 text-white/60 hover:text-white text-4xl leading-none
                       w-12 h-12 flex items-center justify-center rounded-full
                       bg-black/30 hover:bg-black/60 transition select-none">
            ‹
          </button>
        )}

        {/* Loading / error */}
        {loading && !error && (
          <div className="absolute inset-0 flex items-center justify-center text-muted text-sm pointer-events-none">
            <span className="inline-block w-6 h-6 border-2 border-muted border-t-accent rounded-full animate-spin mr-2" />
            Načítám…
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-bad text-sm pointer-events-none">
            Nelze načíst náhled
          </div>
        )}

        <img
          key={photo.id}
          src={previewUrl(photo)}
          alt={photo.name}
          onClick={e => e.stopPropagation()}
          onLoad={() => setLoading(false)}
          onError={() => { setLoading(false); setError(true) }}
          className="max-h-full max-w-full object-contain select-none"
          style={{
            maxHeight: 'calc(100vh - 52px)',
            opacity: loading || error ? 0 : 1,
            transition: 'opacity 0.15s',
          }}
        />

        {/* Right arrow */}
        {index < photos.length - 1 && (
          <button
            onClick={e => { e.stopPropagation(); onNavigate(index + 1) }}
            className="absolute right-3 z-10 text-white/60 hover:text-white text-4xl leading-none
                       w-12 h-12 flex items-center justify-center rounded-full
                       bg-black/30 hover:bg-black/60 transition select-none">
            ›
          </button>
        )}
      </div>
    </div>
  )
}