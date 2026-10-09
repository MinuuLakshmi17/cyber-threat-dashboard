const API_BASE = import.meta.env.VITE_API_BASE || '/api';
async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = await response.json(); message = body.detail || message; } catch { /* retain generic error */ }
    throw new Error(message);
  }
  return response.json();
}
export const api = {
  alerts: (filters = {}) => { const params = new URLSearchParams(); Object.entries(filters).forEach(([k,v]) => { if (v !== '' && v != null) params.set(k, v); }); return request(`/v1/alerts?${params}`); },
  summary: () => request('/v1/analytics/summary'),
  trends: (days = 7) => request(`/v1/analytics/trends?days=${days}`),
  types: () => request('/v1/analytics/types'),
  updateAlert: (id, body) => request(`/v1/alerts/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  createAlert: (body) => request('/v1/alerts', { method: 'POST', body: JSON.stringify(body) }),
};
