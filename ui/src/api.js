// API helper — attaches the ARO API key when one is configured.
//
// The server enforces auth on /api/ routes when the ARO_API_KEY env var is
// set. Store the matching key in the browser once via:
//   localStorage.setItem('aro_api_key', '<your key>')
// Regular requests send it as an X-API-Key header; the SSE stream uses a
// query parameter because EventSource cannot send custom headers.

export const getApiKey = () => {
  try {
    return localStorage.getItem('aro_api_key') || ''
  } catch {
    return ''
  }
}

export const apiFetch = (url, options = {}) => {
  const key = getApiKey()
  const headers = { ...(options.headers || {}) }
  if (key) headers['X-API-Key'] = key
  return fetch(url, { ...options, headers })
}

export const streamUrl = (url) => {
  const key = getApiKey()
  if (!key) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}api_key=${encodeURIComponent(key)}`
}
