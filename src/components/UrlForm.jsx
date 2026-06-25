import { useState } from 'react'

export default function UrlForm({ onSubmit, loading, hideWcagVersion = false }) {
  const [url, setUrl]                 = useState('')
  const [wcagVersion, setWcagVersion] = useState('2.2')
  const [lang, setLang]               = useState('en')

  function handleSubmit(e) {
    e.preventDefault()
    const trimmed = url.trim()
    if (!trimmed) return
    onSubmit({ url: trimmed, wcagVersion, lang })
  }

  return (
    <form className="url-form" onSubmit={handleSubmit}>
      <div className="field field-url">
        <label htmlFor="url-input">Website URL</label>
        <input
          id="url-input"
          type="text"
          placeholder="https://example.com"
          value={url}
          onChange={e => setUrl(e.target.value)}
          disabled={loading}
        />
      </div>

      {!hideWcagVersion && (
        <div className="field">
          <label htmlFor="wcag-version">WCAG Version</label>
          <select
            id="wcag-version"
            value={wcagVersion}
            onChange={e => setWcagVersion(e.target.value)}
            disabled={loading}
          >
            <option value="2.2">WCAG 2.2 (86 criteria)</option>
            <option value="2.1">WCAG 2.1 (78 criteria)</option>
          </select>
        </div>
      )}

      <div className="field">
        <label htmlFor="lang-select">Output Language</label>
        <select
          id="lang-select"
          value={lang}
          onChange={e => setLang(e.target.value)}
          disabled={loading}
        >
          <option value="en">English</option>
          <option value="ja">日本語</option>
        </select>
      </div>

      <button className="btn-run" type="submit" disabled={loading || !url.trim()}>
        {loading ? 'Analysing…' : 'Run Analysis'}
      </button>
    </form>
  )
}
