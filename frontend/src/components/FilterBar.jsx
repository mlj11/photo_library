import { useState, useRef } from 'react'

function Btn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`text-[0.65rem] px-2 py-1 rounded border transition whitespace-nowrap
        ${active
          ? 'border-accent text-accent bg-accent/7'
          : 'border-border text-muted hover:border-accent/50 hover:text-txt'}`}>
      {children}
    </button>
  )
}

const CATS = [
  { k: 'all', label: 'Vše' },
  { k: 'portret_blizky', label: 'Portret-B' },
  { k: 'portret_vzdaleny', label: 'Portret-V' },
  { k: 'krajina', label: 'Krajina' },
  { k: 'detail', label: 'Detail' },
  { k: 'akce', label: 'Akce' },
  { k: 'scena', label: 'Scena' },
]

const SPECIALS = [
  { k: 'all', label: 'Vše' },
  { k: 'best', label: 'Nejlepší ve skupině' },
  { k: 'unique', label: 'Unikátní' },
  { k: 'dof', label: 'DOF/Bokeh' },
  { k: 'blur', label: 'Rozmazané' },
  { k: 'sharp', label: 'Ostré' },
  { k: 'smile', label: 'Úsměv' },
  { k: 'wow', label: 'Překvapení' },
  { k: 'bad_face', label: 'Špatný výraz' },
  { k: 'top25', label: 'Top 25%' },
  { k: 'bot25', label: 'Spodních 25%' },
  { k: 'selected', label: 'Vybrané' },
]

const SORTS = [
  { k: 'name', label: 'Název' },
  { k: 'score', label: 'Score' },
  { k: 'sharp', label: 'Ostrost' },
  { k: 'group', label: 'Skupina' },
  { k: 'rating', label: 'Hodnocení' },
]

export default function FilterBar({ filters, stats, visibleCount, onFiltersChange, onCardSizeChange, cardSize }) {
  const searchRef = useRef(null)
  const [localSearch, setLocalSearch] = useState(filters.search || '')
  const timerRef = useRef(null)

  const set = (key, val) => onFiltersChange(prev => ({ ...prev, [key]: val }))
  const toggleOrder = () => set('order', filters.order === 'asc' ? 'desc' : 'asc')

  function handleSearchChange(e) {
    const v = e.target.value
    setLocalSearch(v)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => set('search', v), 350)
  }

  const scoreMin = stats?.score_min ?? 0
  const scoreMax = stats?.score_max ?? 1
  const scoreRange = scoreMax - scoreMin || 1e-9
  const sliderPct = filters.min_score != null
    ? Math.round((filters.min_score - scoreMin) / scoreRange * 100)
    : 0

  function handleScoreSlider(e) {
    const pct = parseInt(e.target.value)
    set('min_score', pct === 0 ? null : scoreMin + (scoreRange * pct / 100))
  }

  return (
    <div className="bg-surf border-b border-border px-4 py-2 flex flex-col gap-2 sticky top-[57px] z-10">
      {/* Row 1: sort + order + search + count */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-muted text-[0.65rem] min-w-[3rem]">Řazení:</span>
        {SORTS.map(s => (
          <Btn key={s.k} active={filters.sort === s.k} onClick={() => set('sort', s.k)}>{s.label}</Btn>
        ))}
        <button
          onClick={toggleOrder}
          className="text-[0.65rem] px-2 py-1 rounded border border-border text-muted hover:text-txt hover:border-accent/50 transition">
          {filters.order === 'desc' ? '↓ DESC' : '↑ ASC'}
        </button>
        <input
          ref={searchRef}
          type="text"
          placeholder="Hledat název..."
          value={localSearch}
          onChange={handleSearchChange}
          className="ml-2 bg-bg border border-border rounded px-2 py-1 text-[0.65rem] text-txt outline-none focus:border-accent w-36"
        />
        <span className="ml-auto text-muted text-[0.65rem]">
          Zobrazeno: <strong className="text-accent">{visibleCount ?? '–'}</strong>
        </span>
      </div>

      {/* Row 2: categories */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-muted text-[0.65rem] min-w-[3rem]">Kategorie:</span>
        {CATS.map(c => (
          <Btn key={c.k} active={filters.category === c.k} onClick={() => set('category', c.k)}>
            {c.label}
            {stats?.categories?.[c.k] ? <span className="ml-1 text-muted text-[0.55rem]">({stats.categories[c.k]})</span> : null}
          </Btn>
        ))}
      </div>

      {/* Row 3: special filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-muted text-[0.65rem] min-w-[3rem]">Filtr:</span>
        {SPECIALS.map(s => (
          <Btn key={s.k} active={filters.special === s.k} onClick={() => set('special', s.k)}>{s.label}</Btn>
        ))}
      </div>

      {/* Row 4: rating filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-muted text-[0.65rem] min-w-[3rem]">Hodnocení:</span>
        <Btn active={filters.rating === -1} onClick={() => set('rating', -1)}>Vše</Btn>
        <Btn active={filters.rating === 0}  onClick={() => set('rating', 0)}>Nehodnocené</Btn>

        {/* Operator — visible only when 1–5 stars selected */}
        {[1,2,3,4,5].map(n => (
          <Btn key={n} active={filters.rating === n} onClick={() => set('rating', n)}>
            {'★'.repeat(n)}
          </Btn>
        ))}
        {filters.rating >= 1 && (
          <div className="flex gap-1 ml-1">
            {[['eq','='],['gte','≥'],['lte','≤']].map(([op, label]) => (
              <button
                key={op}
                onClick={() => set('rating_op', op)}
                className={`text-[0.65rem] w-6 h-6 rounded border transition
                  ${filters.rating_op === op
                    ? 'border-accent text-accent bg-accent/10'
                    : 'border-border text-muted hover:border-accent/50 hover:text-txt'}`}>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Row 5: score slider + card size */}
      <div className="flex items-center gap-4 flex-wrap">
        <span className="text-muted text-[0.65rem]">Min score:</span>
        <div className="flex items-center gap-2">
          <input type="range" min="0" max="100" value={sliderPct} onChange={handleScoreSlider} className="w-28" />
          <span className="text-muted text-[0.65rem] w-8">{sliderPct}%</span>
        </div>
        <span className="text-muted text-[0.65rem] ml-4">Velikost karet:</span>
        <div className="flex items-center gap-2">
          <input
            type="range" min="150" max="600" step="10" value={cardSize}
            onChange={e => onCardSizeChange(parseInt(e.target.value))}
            className="w-24"
          />
          <span className="text-muted text-[0.65rem] w-10">{cardSize}px</span>
        </div>
        {stats && (
          <span className="text-muted text-[0.6rem] ml-2">
            avg: <strong className="text-txt">{stats.score_avg?.toFixed(3)}</strong>
            &nbsp;|&nbsp;vyb: <strong className="text-accent">{stats.selected}</strong>
            &nbsp;|&nbsp;sk: <strong className="text-txt">{stats.groups}</strong>
            &nbsp;|&nbsp;DOF: <strong className="text-txt">{stats.dof}</strong>
          </span>
        )}
      </div>
    </div>
  )
}
