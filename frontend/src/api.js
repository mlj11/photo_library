const BASE = ''

async function req(url, opts = {}) {
  const r = await fetch(BASE + url, opts)
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText)
    throw new Error(text || r.statusText)
  }
  return r.json()
}

export const api = {
  getSessions: () =>
    req('/api/sessions'),

  createSession: (data) =>
    req('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  getJobs: () =>
    req('/api/jobs'),

  getJobStatus: (jobId) =>
    req(`/api/jobs/${jobId}`),

  getSession: (id) =>
    req(`/api/sessions/${id}`),

  deleteSession: (id) =>
    req(`/api/sessions/${id}`, { method: 'DELETE' }),

  getPhotos: (id, params = {}) => {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
    ).toString()
    return req(`/api/sessions/${id}/photos${qs ? '?' + qs : ''}`)
  },

  updatePhoto: (id, data) =>
    req(`/api/photos/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  getStats: (id) =>
    req(`/api/sessions/${id}/stats`),

  exportSession: (id, data) =>
    req(`/api/sessions/${id}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  openFile: (path) =>
    req(`/api/open?path=${encodeURIComponent(path)}`),

  getScanConfig: () =>
    req('/api/scan-config'),

  saveScanConfig: (data) =>
    req('/api/scan-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  regroupSession: (id) =>
    req(`/api/sessions/${id}/regroup`, { method: 'POST' }),
}
