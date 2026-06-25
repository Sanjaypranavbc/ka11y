/**
 * Calls POST /api/v1/analyse-url-demo on the Node.js server.
 * Vite proxies /api → http://localhost:3000 in dev.
 */
export async function analyseUrl(url, wcagVersion = '2.2', lang = 'en') {
  const res = await fetch('/api/v1/analyse-url-wcag', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, wcagVersion, lang }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.message || data.error || `HTTP ${res.status}`)
  return data
}

/**
 * Calls POST /api/v1/analyse-url — returns raw rule results array.
 * Response: { url, results: [{ successCriteriaId, rules: [...] }] }
 */
export async function analyseUrlRaw(url, lang = 'en') {
  const res = await fetch('/api/v1/analyse-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, lang }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.message || data.error || `HTTP ${res.status}`)
  return data
}

/**
 * Calls POST /api/v1/analyse-url/report — returns a self-contained HTML
 * accessibility report with page screenshot and bounding-box overlays.
 */
export async function fetchReport(url, lang = 'en') {
  const res = await fetch('/api/v1/analyse-url/report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, lang }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.message || data.error || `HTTP ${res.status}`)
  }
  return res.text()
}
