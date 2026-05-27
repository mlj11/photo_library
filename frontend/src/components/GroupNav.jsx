import { useEffect } from 'react'

export default function GroupNav({ photos, activeGroupId, onGroupChange }) {
  const groupMap = {}
  for (const p of photos) {
    if (p.group_id >= 0) {
      groupMap[p.group_id] = (groupMap[p.group_id] || 0) + 1
    }
  }
  const groupIds = Object.keys(groupMap).map(Number).sort((a, b) => a - b)

  // Keyboard navigation
  useEffect(() => {
    function onKey(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      if (e.key === 'ArrowRight') {
        const idx = groupIds.indexOf(activeGroupId)
        const next = groupIds[Math.min(idx + 1, groupIds.length - 1)]
        if (next !== undefined) onGroupChange(next)
      } else if (e.key === 'ArrowLeft') {
        const idx = groupIds.indexOf(activeGroupId)
        if (idx <= 0) onGroupChange(-2)
        else onGroupChange(groupIds[idx - 1])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [groupIds, activeGroupId, onGroupChange])

  if (groupIds.length === 0) return null

  function Btn({ gid, label }) {
    const active = activeGroupId === gid
    const hue = gid >= 0 ? (gid * 47) % 360 : 0
    return (
      <button
        onClick={() => onGroupChange(gid)}
        style={gid >= 0 ? {
          borderColor: active ? '#e8a020' : `hsl(${hue},50%,28%)`,
          color: active ? '#e8a020' : `hsl(${hue},65%,60%)`,
        } : {}}
        className={`text-[0.65rem] px-2 py-1 rounded border transition whitespace-nowrap
          ${active
            ? 'border-accent text-accent bg-accent/7'
            : gid < 0 ? 'border-border text-muted hover:border-accent/50 hover:text-txt' : 'bg-surf hover:opacity-80'}`}>
        {label}
      </button>
    )
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-muted text-[0.65rem] min-w-[3rem]">Skupina:</span>
      <Btn gid={-2} label="Vše" />
      <Btn gid={-1} label="Unikátní" />
      {groupIds.map(gid => (
        <Btn key={gid} gid={gid} label={`gr.${gid} (${groupMap[gid]})`} />
      ))}
      <span className="text-muted text-[0.6rem] ml-1">← → pro navigaci</span>
    </div>
  )
}
