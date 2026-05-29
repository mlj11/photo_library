import { useState } from 'react'

const CAT_LABEL = {
  portret_blizky:  'Portrét B',
  portret_stredni: 'Portrét S',
  portret_vzdaleny:'Portrét V',
  krajina: 'Krajina',
  detail:  'Detail',
  akce:    'Akce',
  scena:   'Scéna',
}

function StarRating({ value, onChange }) {
  const [hover, setHover] = useState(0)
  return (
    <div className="flex gap-0.5 mt-1">
      {[1, 2, 3, 4, 5].map(n => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n === value ? 0 : n)}
          onMouseEnter={() => setHover(n)}
          onMouseLeave={() => setHover(0)}
          className="text-xs leading-none"
          style={{ color: n <= (hover || value) ? '#e8a020' : '#2e2e3e' }}>
          ★
        </button>
      ))}
    </div>
  )
}

function Badge({ type, children }) {
  const styles = {
    cat:   'bg-accent2/10 text-accent2',
    best:  'bg-accent/15 text-accent font-bold',
    grp:   'bg-white/5 text-muted',
    dof:   'bg-purple-500/15 text-purple-400',
    sharp: 'bg-good/12 text-good',
    blur:  'bg-bad/12 text-bad',
    smile:      'bg-good/15 text-green-400 font-semibold',
    wow:        'bg-yellow-500/15 text-yellow-400 font-semibold',
    bad:        'bg-bad/12 text-bad',
    gaze_away:  'bg-orange-500/12 text-orange-400',
  }
  return (
    <span className={`text-[0.58rem] px-1 py-0.5 rounded ${styles[type] || 'text-muted'}`}>
      {children}
    </span>
  )
}

export default function PhotoCard({ photo, scoreMin, scoreMax, onToggleSelect, onOpenLightbox, onUpdate }) {
  const [notes, setNotes] = useState(photo.notes || '')
  const [editingNotes, setEditingNotes] = useState(false)
  const [imgError, setImgError] = useState(false)

  const range = scoreMax - scoreMin || 1e-9
  const scorePct = Math.max(0, Math.min(100, (photo.score - scoreMin) / range * 100))

  const grpStyle = photo.group_id >= 0 ? {
    '--grp-color': `hsl(${(photo.group_id * 47) % 360},60%,7%)`,
    '--grp-border': `hsl(${(photo.group_id * 47) % 360},50%,20%)`,
  } : {}

  async function handleRating(r) {
    await onUpdate(photo.id, { user_rating: r })
  }

  async function handleNotesSave() {
    await onUpdate(photo.id, { notes })
    setEditingNotes(false)
  }

  const displayCat = photo.user_category || photo.category

  return (
    <div
      className={`bg-surf border rounded-lg overflow-hidden transition-all duration-100
        hover:-translate-y-0.5 hover:shadow-xl
        ${photo.selected ? 'border-accent shadow-[0_0_0_2px_rgba(232,160,32,0.3)]' : 'border-border hover:border-accent/50'}
        ${photo.group_id >= 0 ? 'card-in-group' : ''}`}
      style={grpStyle}>

      {/* Thumbnail */}
      <div
        className="relative aspect-[3/2] overflow-hidden bg-bg cursor-pointer group"
        onClick={onOpenLightbox}>
        {!imgError ? (
          <img
            src={photo.thumb_url}
            alt={photo.name}
            loading="lazy"
            onError={() => setImgError(true)}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-muted text-xs">
            No thumb
          </div>
        )}
        <div className="absolute inset-0 bg-black/45 opacity-0 group-hover:opacity-100 transition-opacity
                        flex items-center justify-center text-white">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
        </div>
      </div>

      {/* Info */}
      <div className="px-2 pt-1.5 pb-2 flex flex-col gap-1">
        {/* Score */}
        <div className="flex items-center gap-1.5">
          <span className="text-accent font-bold text-[0.82rem] min-w-[3.2rem]">
            {photo.score.toFixed(4)}
          </span>
          <div className="score-bar flex-1">
            <div className="score-fill" style={{ width: `${scorePct}%` }} />
          </div>
        </div>

        {/* Filename */}
        <div className="text-muted text-[0.63rem] truncate" title={photo.name}>{photo.name}</div>

        {/* Metrics */}
        <div className="text-[0.58rem] text-muted/60">
          clip:{photo.clip_score.toFixed(3)} sh:{photo.sharp_center.toFixed(0)}/{photo.sharp_edges.toFixed(0)} comp:{photo.comp_score >= 0 ? '+' : ''}{photo.comp_score.toFixed(2)}
        </div>

        {/* Badges */}
        <div className="flex flex-wrap gap-0.5">
          <Badge type="cat">{CAT_LABEL[displayCat] || displayCat}</Badge>
          {photo.group_id >= 0 && photo.best_in_group && <Badge type="best">★ gr.{photo.group_id}</Badge>}
          {photo.group_id >= 0 && !photo.best_in_group && <Badge type="grp">gr.{photo.group_id}</Badge>}
          {photo.dof && <Badge type="dof">bokeh</Badge>}
          {photo.sharp_center > 200 && <Badge type="sharp">ostrá</Badge>}
          {photo.sharp_center < 60 && photo.sharp_total < 60 && !photo.dof && <Badge type="blur">rozm.</Badge>}
          {photo.emotion === 'smile' && <Badge type="smile">úsměv</Badge>}
          {photo.emotion === 'wow' && <Badge type="wow">překvapení</Badge>}
          {photo.emotion === 'bad' && <Badge type="bad">šp.výraz</Badge>}
          {photo.gaze === 'away' && <Badge type="gaze_away">bokem</Badge>}
        </div>

        {/* Star rating */}
        <StarRating value={photo.user_rating} onChange={handleRating} />

        {/* Notes */}
        {editingNotes ? (
          <div className="flex gap-1 mt-0.5">
            <input
              className="flex-1 bg-bg border border-border rounded px-1.5 py-0.5 text-[0.6rem] text-txt outline-none focus:border-accent"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleNotesSave(); if (e.key === 'Escape') setEditingNotes(false) }}
              autoFocus
            />
            <button onClick={handleNotesSave} className="text-[0.6rem] text-accent px-1">OK</button>
          </div>
        ) : (
          <button
            onClick={() => setEditingNotes(true)}
            className="text-[0.6rem] text-muted hover:text-txt text-left truncate mt-0.5">
            {photo.notes ? `📝 ${photo.notes}` : '+ poznámka'}
          </button>
        )}

        {/* Select checkbox */}
        <label
          className="flex items-center gap-1.5 mt-1 pt-1.5 border-t border-border cursor-pointer"
          onClick={e => e.stopPropagation()}>
          <input
            type="checkbox"
            checked={photo.selected}
            onChange={e => onToggleSelect(photo.id, e.target.checked)}
            className="w-3.5 h-3.5 flex-shrink-0"
          />
          <span className={`text-[0.62rem] select-none ${photo.selected ? 'text-accent' : 'text-muted'}`}>
            Vybrat
          </span>
        </label>
      </div>
    </div>
  )
}
