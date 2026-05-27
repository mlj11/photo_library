import { useState } from 'react'
import { api } from '../api'

export default function SelectionBar({ selectedPhotos, allPhotos, sessionId, onClear, onSelectVisible }) {
  const [destDir, setDestDir] = useState('')
  const [showExport, setShowExport] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [result, setResult] = useState(null)

  const n = selectedPhotos.length
  if (n === 0) return null

  async function handleExport() {
    if (!destDir.trim()) return
    setExporting(true)
    setResult(null)
    try {
      const res = await api.exportSession(sessionId, {
        dest_dir: destDir.trim(),
        only_selected: true,
      })
      setResult(res)
    } catch (e) {
      setResult({ error: e.message })
    } finally {
      setExporting(false)
    }
  }

  const preview = selectedPhotos.slice(0, 4).map(p => p.name).join(', ')
  const more = n > 4 ? ` +${n - 4} dalších` : ''

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-surf border-t border-accent z-50">
      {showExport && (
        <div className="px-6 py-3 border-b border-border flex items-center gap-3 flex-wrap">
          <span className="text-muted text-xs">Cílová složka:</span>
          <input
            className="flex-1 min-w-48 bg-bg border border-border rounded px-3 py-1.5 text-sm text-txt font-mono outline-none focus:border-accent"
            placeholder="Z:\Foto\Vyber"
            value={destDir}
            onChange={e => setDestDir(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleExport()}
          />
          <button
            onClick={handleExport}
            disabled={exporting || !destDir.trim()}
            className="bg-accent text-black text-xs font-bold px-4 py-1.5 rounded hover:bg-yellow-400 transition disabled:opacity-50">
            {exporting ? 'Kopíruju...' : `Kopírovat ${n} fotek`}
          </button>
          <button onClick={() => { setShowExport(false); setResult(null) }}
            className="text-muted text-xs hover:text-txt">✕</button>
          {result && !result.error && (
            <span className="text-good text-xs">
              ✓ Zkopírováno {result.copied}/{result.total} do {result.dest}
              {result.errors?.length > 0 && ` (${result.errors.length} chyb)`}
            </span>
          )}
          {result?.error && <span className="text-bad text-xs">{result.error}</span>}
        </div>
      )}

      <div className="px-6 py-2 flex items-center gap-3 flex-wrap">
        <span className="text-accent font-bold text-sm">{n} vybráno</span>
        <span className="text-muted text-xs flex-1 truncate">{preview}{more}</span>
        <button
          onClick={onSelectVisible}
          className="text-xs px-3 py-1.5 rounded border border-border text-muted hover:text-txt hover:border-accent/50 transition">
          Vybrat viditelné
        </button>
        <button
          onClick={onClear}
          className="text-xs px-3 py-1.5 rounded border border-border text-muted hover:text-txt hover:border-accent/50 transition">
          Zrušit výběr
        </button>
        <button
          onClick={() => setShowExport(v => !v)}
          className="text-xs px-4 py-1.5 rounded bg-accent text-black font-bold hover:bg-yellow-400 transition">
          Exportovat vybrané →
        </button>
      </div>
    </div>
  )
}
