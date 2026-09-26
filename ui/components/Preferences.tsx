import { useEffect, useState } from 'react';
import { api } from '../api';
import { useUnsavedChanges } from './Unsaved';

interface Preference {id: string; category: string; value: string}
export function Preferences({onDirtyChange}:{onDirtyChange?:(dirty:boolean)=>void}) {
  const [items, setItems] = useState<Preference[]>([]), [error, setError] = useState('');
  const [category, setCategory] = useState('communication'), [value, setValue] = useState(''), [editing, setEditing] = useState('');
  const [busy, setBusy] = useState(false);
  useUnsavedChanges(!!value.trim());
  useEffect(()=>{onDirtyChange?.(!!value.trim());return()=>onDirtyChange?.(false);},[value,onDirtyChange]);
  async function refresh() {setItems(await api<Preference[]>('/preferences'));}
  useEffect(() => {void refresh().catch(e => setError(e.message));}, []);
  async function save() {
    setBusy(true); setError('');
    try {await api(`/preferences${editing ? '/' + editing : ''}`, {method: editing ? 'PATCH' : 'POST', body: JSON.stringify({category, value})}); setEditing(''); setValue(''); await refresh();}
    catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function forget(id: string) {
    if (!window.confirm('Forget this approved preference?')) return;
    try {await api(`/preferences/${id}`, {method:'DELETE', headers:{'X-Stonic-Confirm':'delete'}}); await refresh();} catch(e) {setError((e as Error).message);}
  }
  return <section className="preferences-editor"><h3>Approved preferences</h3><p className="muted">Save corrections and preferences here. They influence future conversations when learning is enabled above.</p>
    {error && <p className="error-box" role="alert">{error}</p>}
    <label>Preference category<select value={category} onChange={e => setCategory(e.target.value)}>{['communication','applications','workflow','gaming'].map(c => <option key={c}>{c}</option>)}</select></label>
    <label>Preference<textarea aria-label="Preference" maxLength={1000} rows={3} value={value} onChange={e => setValue(e.target.value)} placeholder="For example: keep responses brief unless I ask for detail."/></label>
    <div className="action-row"><button className="secondary-button" disabled={busy || !value.trim()} onClick={() => void save()}>{editing ? 'Save correction' : 'Approve and save'}</button>{editing && <button className="text-button" onClick={() => {setEditing(''); setValue('');}}>Cancel edit</button>}</div>
    {!items.length && <p className="muted">No approved preferences yet.</p>}
    {items.map(item => <article className="job-card" key={item.id}><span className="micro-tag">{item.category}</span><p>{item.value}</p><div className="action-row"><button className="text-button" onClick={() => {setEditing(item.id); setCategory(item.category); setValue(item.value);}}>Edit</button><button className="text-button" onClick={() => void forget(item.id)}>Forget</button></div></article>)}
  </section>;
}
