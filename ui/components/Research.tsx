import { useEffect, useState } from 'react';
import { api } from '../api';
interface Report {id: string; query: string; mode: string; retrieved_at: string; answer: string; sources: {title: string; url: string; snippet: string}[]}

export function Research() {
  const [query, setQuery] = useState(''), [mode, setMode] = useState('quick'), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [reports, setReports] = useState<Report[]>([]), [selected, setSelected] = useState<Report | null>(null);
  useEffect(() => {api<Report[]>('/research').then(setReports).catch(e => setError(e.message));}, []);
  async function search(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {const result = await api<{success: boolean; message: string; data: Report}>('/research', {method:'POST', body:JSON.stringify({query, mode})}); if (!result.success) throw new Error(result.message); setSelected(result.data); setReports(old => [result.data, ...old]);}
    catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  return <div className="domain-content"><form className="research-form" onSubmit={e => void search(e)}><label>Research question<input required minLength={3} maxLength={3000} value={query} onChange={e => setQuery(e.target.value)} placeholder="What would you like to find out?"/></label><label>Depth<select value={mode} onChange={e => setMode(e.target.value)}><option value="quick">Quick search</option><option value="research">Research</option><option value="deep">Deep research</option></select></label><button className="primary-button" disabled={busy}>{busy ? 'Researching…' : 'Search live web'}</button>{busy && <button type="button" className="text-button" onClick={() => void api('/chat/cancel', {method:'POST'})}>Stop research</button>}</form>
    {error && <p className="error-box" role="alert">{error}</p>}
    {selected ? <article className="research-report"><h3>{selected.query}</h3><small>{selected.mode} · Retrieved {new Date(selected.retrieved_at).toLocaleString()}</small><div className="report-text">{selected.answer}</div><h4>Retrieved sources</h4><div className="source-grid">{selected.sources.map(s => <a key={s.url} href={s.url} target="_blank" rel="noreferrer"><strong>{s.title}</strong><small>{new URL(s.url).hostname}</small><p>{s.snippet.slice(0,220)}</p></a>)}</div></article> : <p className="muted">Search current information with source links, or open an earlier report.</p>}
    <div className="domain-list">{reports.map(r => <button key={r.id} className="report-history" onClick={() => setSelected(r)}>{r.query}<small>{new Date(r.retrieved_at).toLocaleDateString()}</small></button>)}</div>
  </div>;
}
