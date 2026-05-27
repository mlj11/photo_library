import { useEffect, useRef } from 'react'

export default function GroupNav({ groupCounts = {}, activeGroupId, onGroupChange }) {
  const groupIds = Object.keys(groupCounts).map(Number).sort((a, b) => a - b)

  // Stable ref so the keydown handler always sees current values without re-registering
  const stateRef = useRef({ groupIds, activeGroupId, onGroupChange })
  useEffect(() => {
    stateRef.current = { groupIds, activeGroupId, onGroupChange }
  })

  useEffect(() => {
    function onKey(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return
      const { groupIds, activeGroupId, onGroupChange } = stateRef.current
      const all = [-2, -1, ...groupIds]
      const idx = all.indexOf(activeGroupId)
      if (e.key === 'ArrowRight' && idx < all.length - 1) onGroupChange(all[idx + 1])
      else if (e.key === 'ArrowLeft' && idx > 0) onGroupChange(all[idx - 1])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, []) // registruje se jednou, čte aktuální stav přes ref

  if (groupIds.length === 0) return null

  return (
    <div className="flex items-center gap-2">
      <span className="text-muted text-[0.65rem] whitespace-nowrap">Skupina:</span>
      <select
        value={activeGroupId}
        onChange={e => onGroupChange(Number(e.target.value))}
        className="bg-bg border border-border rounded px-2 py-1 text-xs text-txt focus:border-accent outline-none cursor-pointer">
        <option value={-2}>Vše</option>
        <option value={-1}>Unikátní</option>
        {groupIds.map(gid => (
          <option key={gid} value={gid}>gr.{gid} ({groupCounts[gid]})</option>
        ))}
      </select>
      <span className="text-muted text-[0.6rem]">← → pro navigaci</span>
    </div>
  )
}