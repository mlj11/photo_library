import { useState, useEffect } from 'react'
import { api } from '../api'

const FIELDS = [
  {
    group: 'CLIP model',
    items: [
      {
        key: 'clip_model', label: 'Model', type: 'select',
        options: [
          { value: 'ViT-L/14', label: 'ViT-L/14 — přesný (výchozí, ~900 MB)' },
          { value: 'ViT-B/32', label: 'ViT-B/32 — rychlý (~350 MB)' },
        ],
        desc: 'Větší model = lepší rozpoznání obsahu, ale pomalejší načítání.',
      },
    ],
  },
  {
    group: 'Kvalita skóre',
    items: [
      {
        key: 'neg_weight', label: 'Váha negativních promptů', type: 'range',
        min: 0.3, max: 1.2, step: 0.05, fmt: v => v.toFixed(2),
        desc: 'Jak silně negativní prompty (rozmazané, tmavé…) snižují skóre. Výchozí 0.70.',
      },
    ],
  },
  {
    group: 'Duplikáty & skupiny',
    items: [
      {
        key: 'dedup_threshold', label: 'CLIP podobnost', type: 'range',
        min: 0.80, max: 0.99, step: 0.01, fmt: v => v.toFixed(2),
        desc: 'Min. kosinová podobnost CLIP embeddingů pro zařazení do stejné skupiny. Výchozí 0.92.',
      },
      {
        key: 'phash_threshold', label: 'pHash podobnost', type: 'range',
        min: 0.65, max: 0.95, step: 0.01, fmt: v => v.toFixed(2),
        desc: 'Min. podobnost perceptuálního hashe. Nižší = toleruje větší pohyb osoby. Výchozí 0.83.',
      },
    ],
  },
  {
    group: 'Ostrost & DOF / bokeh',
    items: [
      {
        key: 'dof_peak_min', label: 'Min. ostrost pro detekci bokeh', type: 'range',
        min: 30, max: 400, step: 10, fmt: v => Math.round(v),
        desc: 'Laplaciánova variance nejostřejšího bloku musí překročit tuto hodnotu. Výchozí 120.',
      },
      {
        key: 'dof_ratio', label: 'Poměr peak/median pro bokeh', type: 'range',
        min: 1.5, max: 6.0, step: 0.1, fmt: v => v.toFixed(1),
        desc: 'Nejostřejší blok musí být X× ostřejší než medián bloků. Výchozí 2.5.',
      },
      {
        key: 'blur_penalty_thr', label: 'Práh penalizace za rozmazání', type: 'range',
        min: 10, max: 150, step: 5, fmt: v => Math.round(v),
        desc: 'Pod touto hodnotou variance dostane foto penalizaci za celkové rozmazání. Výchozí 40.',
      },
    ],
  },
  {
    group: 'Přeskočit soubory',
    items: [
      {
        key: 'skip_files', label: 'Přeskočit soubory', type: 'textarea',
        desc: 'Názvy souborů k přeskočení (jeden na řádek). Např. soubory které způsobují crash rawpy.',
      },
    ],
  },
  {
    group: 'Náhledy',
    items: [
      {
        key: 'thumb_size', label: 'Velikost náhledů (px)', type: 'range',
        min: 150, max: 800, step: 50, fmt: v => Math.round(v) + ' px',
        desc: 'Delší strana náhledu v pixelech. Větší = lepší kvalita, pomalejší scan.',
      },
      {
        key: 'sort', label: 'Výchozí řazení', type: 'select',
        options: [
          { value: 'name',  label: 'Název souboru' },
          { value: 'score', label: 'Skóre (sestupně)' },
          { value: 'sharp', label: 'Ostrost (sestupně)' },
        ],
        desc: 'Jak jsou fotky seřazeny ve výstupu HTML dashboardu.',
      },
    ],
  },
]

export default function SettingsModal({ onClose }) {
  const [config, setConfig] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getScanConfig().then(setConfig).catch(e => setError(e.message))
  }, [])

  function set(key, value) {
    setConfig(c => ({ ...c, [key]: value }))
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    setError('')
    try {
      const saved = await api.saveScanConfig(config)
      setConfig(saved)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/75 flex items-start justify-center z-50 overflow-y-auto py-8"
         onClick={onClose}>
      <div className="bg-surf border border-border rounded-lg w-full max-w-lg mx-4"
           onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="font-syne text-accent font-bold text-base">Nastavení scanu</h2>
          <button onClick={onClose} className="text-muted hover:text-txt text-lg leading-none">✕</button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 flex flex-col gap-5 max-h-[70vh] overflow-y-auto">
          {!config && !error && (
            <p className="text-muted text-sm text-center py-4">Načítám...</p>
          )}
          {error && <p className="text-bad text-xs">{error}</p>}

          {config && FIELDS.map(({ group, items }) => (
            <div key={group}>
              <p className="text-accent text-[0.65rem] font-bold uppercase tracking-wider mb-2">{group}</p>
              <div className="flex flex-col gap-3">
                {items.map(f => (
                  <div key={f.key}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-txt text-xs">{f.label}</span>
                      {f.type !== 'textarea' && (
                        <span className="text-accent text-xs font-bold font-mono">
                          {f.fmt ? f.fmt(config[f.key]) : config[f.key]}
                        </span>
                      )}
                    </div>

                    {f.type === 'range' && (
                      <input
                        type="range"
                        min={f.min} max={f.max} step={f.step}
                        value={config[f.key]}
                        onChange={e => set(f.key, parseFloat(e.target.value))}
                        className="w-full h-1 bg-border rounded appearance-none cursor-pointer accent-accent"
                      />
                    )}

                    {f.type === 'select' && (
                      <select
                        value={config[f.key]}
                        onChange={e => set(f.key, e.target.value)}
                        className="w-full bg-bg border border-border rounded px-2 py-1.5 text-xs text-txt focus:border-accent outline-none cursor-pointer">
                        {f.options.map(o => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    )}

                    {f.type === 'textarea' && (
                      <textarea
                        rows={4}
                        value={(config[f.key] || []).join('\n')}
                        onChange={e => set(f.key, e.target.value.split('\n').map(s => s.trim()).filter(Boolean))}
                        placeholder="S3_06811.ARW"
                        className="w-full bg-bg border border-border rounded px-2 py-1.5 text-xs text-txt font-mono focus:border-accent outline-none resize-none"
                      />
                    )}

                    <p className="text-muted text-[0.6rem] mt-1">{f.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        {config && (
          <div className="px-5 py-3 border-t border-border flex items-center justify-between gap-2">
            <p className="text-[0.6rem] text-muted">Nastavení se projeví u příštího scanu.</p>
            <div className="flex gap-2">
              <button onClick={onClose}
                className="px-3 py-1.5 text-xs bg-border text-txt rounded hover:bg-muted/30 transition">
                Zavřít
              </button>
              <button onClick={handleSave} disabled={saving}
                className="px-4 py-1.5 text-xs bg-accent text-black font-bold rounded hover:bg-yellow-400 transition disabled:opacity-50">
                {saving ? 'Ukládám…' : saved ? '✓ Uloženo' : 'Uložit'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}