import { useEffect, useState } from 'react';
import { Plus, Trash2, Check, Pencil, Search, NotebookPen, ListTodo, Brain, ArrowLeft } from 'lucide-react';
import { api, type WorkspaceRecord } from '../api';
import { useUnsavedChanges } from './Unsaved';

export function Records({ kind, onChange, onDirtyChange }: {kind: 'notes'|'tasks'|'memory'; onChange: () => void; onDirtyChange?: (kind: string, dirty: boolean) => void}) {
  const [records, setRecords] = useState<WorkspaceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState<WorkspaceRecord | 'new' | null>(null);
  const [title, setTitle] = useState(''), [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [memoryType, setMemoryType] = useState('user'), [memoryFilter, setMemoryFilter] = useState('all'); const [memoryConsent, setMemoryConsent] = useState(false);
  const [dirty, setDirty] = useState(false);
  useUnsavedChanges(dirty);
  useEffect(() => {
    onDirtyChange?.(kind, dirty);
    return () => onDirtyChange?.(kind, false);
  }, [kind, dirty, onDirtyChange]);
  const Icon = kind === 'notes' ? NotebookPen : kind === 'tasks' ? ListTodo : Brain;
  const singular = kind === 'memory' ? 'memory' : kind.slice(0, -1);
  async function refresh() {
    try { setRecords(await api<WorkspaceRecord[]>(`/records/${kind}`)); setError(''); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, [kind]);
  useEffect(() => {
    if (!dirty) return;
    const protect = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, [dirty]);
  function edit(record: WorkspaceRecord | 'new') {
    setMemoryType(record === 'new' ? 'user' : record.memory_type || 'user');
    setEditing(record); setTitle(record === 'new' ? '' : record.title); setContent(record === 'new' ? '' : record.content); setMemoryConsent(false); setDirty(false);
  }
  async function save() {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await api(`/records/${kind}${editing !== 'new' && editing ? `/${editing.id}` : ''}`, {
        method: editing === 'new' ? 'POST' : 'PATCH', body: JSON.stringify({ title: title.trim(), content, ...(kind === 'memory' ? {memory_type:memoryType, confirm_memory:memoryConsent} : {}) }),
      });
      setDirty(false); setEditing(null); await refresh(); onChange();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function remove(record: WorkspaceRecord) {
    if (!window.confirm(`Delete “${record.title}”? This removes it from your local workspace.`)) return;
    try { await api(`/records/${kind}/${record.id}`, { method: 'DELETE', headers: {'X-Stonic-Confirm':'delete'} }); await refresh(); onChange(); }
    catch(e) { setError((e as Error).message); }
  }
  async function toggle(record: WorkspaceRecord) {
    try { await api(`/records/${kind}/${record.id}`, { method: 'PATCH', body: JSON.stringify({ status: record.status === 'done' ? 'open' : 'done' }) }); await refresh(); onChange(); }
    catch(e) { setError((e as Error).message); }
  }
  const filtered = records.filter(r => `${r.title} ${r.content}`.toLowerCase().includes(query.toLowerCase()) && (kind !== 'memory' || memoryFilter === 'all' || (r.memory_type || 'user') === memoryFilter));
  return <div className="records-view">
    {error ? <div className="error-box" role="alert">{error}</div> : null}
    {editing ? <form className="record-form" onSubmit={e => { e.preventDefault(); void save(); }}>
      <button className="text-button" type="button" onClick={() => { if (!dirty || window.confirm('Discard your unsaved changes?')) { setEditing(null); setDirty(false); } }}><ArrowLeft size={14}/> Back to {kind}</button>
      <label>Title<input autoFocus aria-label={`${singular} title`} value={title} maxLength={200} required onChange={e => { setTitle(e.target.value); setDirty(true); }} placeholder={kind === 'tasks' ? 'What needs to get done?' : 'Give it a title'} /></label>
      {kind === 'memory' && <label>Memory type<select aria-label="Memory type" value={memoryType} onChange={e => {setMemoryType(e.target.value);setDirty(true);}}>{['user','conversation','task','environment'].map(c => <option key={c}>{c}</option>)}</select></label>}
      {kind === 'memory' && <label className="memory-consent"><input type="checkbox" checked={memoryConsent} onChange={e => {setMemoryConsent(e.target.checked);setDirty(true);}}/> I explicitly want STONIC to retain this on this device.</label>}<label>{kind === 'memory' ? 'What should STONIC remember?' : 'Details'}<textarea aria-label={`${singular} details`} value={content} maxLength={20000} rows={7} onChange={e => { setContent(e.target.value); setDirty(true); }} placeholder="Add a little context…"/></label>
      <button className="primary-button" disabled={busy || !title.trim() || (kind === 'memory' && !memoryConsent)}>{busy ? 'Saving…' : `Save ${singular}`}</button>
    </form> : <>
      {kind === 'memory' && <label className="memory-filter">Memory type<select aria-label="Memory type" value={memoryFilter} onChange={e => setMemoryFilter(e.target.value)}>{['all','user','conversation','task','environment'].map(c => <option key={c}>{c}</option>)}</select></label>}
      <div className="records-toolbar"><div className="search-field"><Search size={14}/><input aria-label={`Search ${kind}`} placeholder={`Search ${kind}…`} value={query} onChange={e => setQuery(e.target.value)}/></div><button className="icon-button add-button" aria-label={`Add ${singular}`} onClick={() => edit('new')}><Plus size={17}/></button></div>
      {loading ? <div className="loading-text">Opening local {kind}…</div> : filtered.length ? <div className="record-list">{filtered.map(record => <article key={record.id} className={`record-card ${record.status === 'done' ? 'record-done' : ''}`}>
        <div className="record-title">{kind === 'tasks' ? <button className={`check-button ${record.status === 'done' ? 'checked' : ''}`} aria-label={record.status === 'done' ? 'Reopen task' : 'Complete task'} onClick={() => void toggle(record)}>{record.status === 'done' ? <Check size={12}/> : null}</button> : null}<h3>{record.title}</h3><button className="icon-button" aria-label={`Edit ${record.title}`} onClick={() => edit(record)}><Pencil size={13}/></button><button className="icon-button" aria-label={`Delete ${record.title}`} onClick={() => void remove(record)}><Trash2 size={13}/></button></div>
        {record.content ? <p>{record.content}</p> : null}<time>{new Date(record.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} · Saved on this device</time>
      </article>)}</div> : <div className="empty-state record-empty"><div className="empty-icon"><Icon size={24}/></div><h3>{query ? 'Nothing matches yet' : kind === 'notes' ? 'Room for a thought' : kind === 'tasks' ? 'A clear horizon' : 'A little context goes a long way'}</h3><p>{query ? 'Try a different search.' : kind === 'memory' ? 'Save a preference, a detail, or something useful for later. Memory stays on this device.' : `Your ${kind} live here, saved privately on this device.`}</p>{!query ? <button className="secondary-button" onClick={() => edit('new')}><Plus size={14}/> Add your first {singular}</button> : null}</div>}
      {kind === 'tasks' ? <div className="record-footnote">Your todos are here. Plans, approvals and execution results appear in Task activity.</div> : null}
    </>}
  </div>;
}
