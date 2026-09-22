import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { Events } from './Events';
import { Briefing } from './Briefing';
import { useUnsavedChanges } from './Unsaved';
interface Schedule {id: string; title: string; due_at: string; interval_seconds: number | null; status: string}
interface Notice {id: string; title: string; body: string; source: string; read: number; created_at: string}

export function Productivity() {
  const [schedules, setSchedules] = useState<Schedule[]>([]), [notices, setNotices] = useState<Notice[]>([]);
  const [title, setTitle] = useState(''), [due, setDue] = useState(''), [repeat, setRepeat] = useState('0');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  useUnsavedChanges(!!title.trim()||!!due);
  const refresh = useCallback(async () => {try {const [s, n] = await Promise.all([api<Schedule[]>('/schedules'), api<Notice[]>('/notifications')]); setSchedules(s); setNotices(n);} catch(e) {setError((e as Error).message);}}, []);
  useEffect(() => {void refresh(); const timer = setInterval(() => void refresh(), 3000); return () => clearInterval(timer);}, [refresh]);
  async function create(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {await api('/schedules', {method: 'POST', body: JSON.stringify({title, due_at: new Date(due).toISOString(), interval_seconds: Number(repeat) || null})}); setTitle(''); setDue(''); await refresh();}
    catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function action(path: string) {try {await api(path, {method: 'POST'}); await refresh();} catch(e) {setError((e as Error).message);}}
  return <div className="domain-content"><Briefing/><h3>Reminders & calendar</h3><p className="muted">Times use your local timezone. Reminders persist when Stonic closes and are delivered when it next runs.</p>
    {error && <p role="alert" className="error-box">{error}</p>}
    <form className="reminder-form" onSubmit={e => void create(e)}><label>Reminder<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="What should I remind you about?"/></label><label>When<input required type="datetime-local" value={due} onChange={e => setDue(e.target.value)}/></label><label>Repeat<select value={repeat} onChange={e => setRepeat(e.target.value)}><option value="0">Once</option><option value="3600">Hourly</option><option value="86400">Every 24 hours</option><option value="604800">Every 7 days</option></select></label><button className="primary-button" disabled={busy}>Save reminder</button></form>
    <div className="domain-list">{schedules.map(s => <article key={s.id}><div><strong>{s.title}</strong><p>{new Date(s.due_at).toLocaleString()} · {s.status}</p></div>{s.status === 'active' && <button className="text-button" onClick={() => void action(`/schedules/${s.id}/cancel`)}>Cancel</button>}</article>)}{!schedules.length && <p className="muted">No reminders scheduled.</p>}</div>
    <h3>Notifications</h3><div className="domain-list">{notices.map(n => <article key={n.id}><div><strong>{n.title}</strong><p>{n.body}</p><small>{new Date(n.created_at).toLocaleString()} · {n.source}</small></div>{!n.read && <button className="text-button" onClick={() => void action(`/notifications/${n.id}/read`)}>Mark read</button>}</article>)}{!notices.length && <p className="muted">You’re all caught up.</p>}</div>
    <Events/>
  </div>;
}
