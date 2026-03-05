/**
 * Willow API helpers
 */

const BASE = '';

export async function fetchStatus() {
  const res = await fetch(`${BASE}/api/status`);
  return res.json();
}

export async function fetchPersonas() {
  const res = await fetch(`${BASE}/api/personas`);
  return res.json();
}

export async function searchKnowledge(query, limit = 5) {
  const res = await fetch(`${BASE}/api/knowledge/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  return res.json();
}

export async function fetchGaps(limit = 10) {
  const res = await fetch(`${BASE}/api/knowledge/gaps?limit=${limit}`);
  return res.json();
}

export async function fetchStats() {
  const res = await fetch(`${BASE}/api/knowledge/stats`);
  return res.json();
}

export async function fetchCoherence() {
  const res = await fetch(`${BASE}/api/coherence`);
  return res.json();
}

export async function ingestFile(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/api/ingest`, { method: 'POST', body: form });
  return res.json();
}

// --- PA (Personal Assistant) ---

export async function paScan() {
  const res = await fetch(`${BASE}/api/pa/scan`, { method: 'POST' });
  return res.json();
}

export async function paPlan() {
  const res = await fetch(`${BASE}/api/pa/plan`);
  return res.json();
}

export async function paExecute(scope) {
  const res = await fetch(`${BASE}/api/pa/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope }),
  });
  return res.json();
}

export async function paStatus() {
  const res = await fetch(`${BASE}/api/pa/status`);
  return res.json();
}

export async function paCorrect({ path, destination, text, category }) {
  const res = await fetch(`${BASE}/api/pa/correct`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, destination, text, category }),
  });
  return res.json();
}
