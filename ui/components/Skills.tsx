import { useEffect, useState } from 'react';
import { api, type Skill } from '../api';

interface Plugin {id: string; name: string; description?: string; version?: string; digest?: string; enabled: boolean; error?: string; config?: Record<string, unknown>; config_schema?: Record<string, unknown>}
interface Routine {id: string; name: string; description: string; params: string[]; status: string; uses: number}
export function Skills({tools}: {tools: Skill[]}) {
  const [catalog,setCatalog]=useState<Skill[]>(tools);
  const [plugins, setPlugins] = useState<Plugin[]>([]), [error, setError] = useState(''), [busy, setBusy] = useState('');
  const [configs, setConfigs] = useState<Record<string, string>>({});
  const [routines, setRoutines] = useState<Routine[]>([]);
  async function refresh() {const [items,registered] = await Promise.all([api<Plugin[]>('/plugins'),api<Skill[]>('/skills')]); setPlugins(items);setCatalog(registered); setConfigs(Object.fromEntries(items.map(p => [p.id, JSON.stringify(p.config || {}, null, 2)])));}
  async function refreshRoutines() {try {setRoutines(await api<Routine[]>('/agent/skills'));} catch { /* agent not enabled */ }}
  useEffect(() => {void refresh().catch(e => setError(e.message)); void refreshRoutines();}, []);
  async function decideRoutine(id: string, approved: boolean) {
    setBusy(id); setError('');
    try {await api(`/agent/skills/${id}/decision`, {method: 'POST', body: JSON.stringify({approved})}); await refreshRoutines();}
    catch(e) {setError((e as Error).message);} finally {setBusy('');}
  }
  async function forgetRoutine(id: string) {
    setBusy(id); setError('');
    try {await api(`/agent/skills/${id}`, {method: 'DELETE'}); await refreshRoutines();}
    catch(e) {setError((e as Error).message);} finally {setBusy('');}
  }
  async function toggle(plugin: Plugin) {
    if (!plugin.enabled && !window.confirm(`Enable ${plugin.name}? This runs trusted local Python code with your Windows user permissions. Review the files in the skills folder first. Every tool invocation will also require approval.`)) return;
    setBusy(plugin.id); setError('');
    try {await api(`/plugins/${plugin.id}`, {method:'PUT', body:JSON.stringify({enabled:!plugin.enabled, digest:plugin.digest, config:JSON.parse(configs[plugin.id] || '{}'), confirm_trusted_code:true})}); await refresh();}
    catch(e) {setError((e as Error).message);} finally {setBusy('');}
  }
  const pendingRoutines = routines.filter(r => r.status === 'pending'), activeRoutines = routines.filter(r => r.status === 'active');
  return <div className="modal-content"><h3>Installed skills</h3><p className="muted">Add a reviewed skill bundle to Stonic’s skills folder, then refresh. Each skill declares its inputs, outputs, permissions and configuration.</p>
    <button className="text-button" onClick={() => void refresh().catch(e => setError(e.message))}>Refresh installed skills</button>
    {error && <p className="error-box" role="alert">{error}</p>}{!plugins.length && <p className="muted">No external skills installed. Built-in tools are available below.</p>}
    {plugins.map(p => <article className="job-card" key={p.id}><div className="job-heading"><h3>{p.name}</h3><span className="micro-tag">{p.enabled ? 'ENABLED' : 'DISABLED'} {p.version}</span></div><p>{p.description}</p>{p.error && <p className="error-box">{p.error}</p>}{p.digest && <><details><summary>Review configuration and bundle fingerprint</summary><pre>{p.digest}</pre><pre>{JSON.stringify(p.config_schema, null, 2)}</pre><label>Skill configuration<textarea aria-label={`${p.name} configuration`} rows={4} value={configs[p.id] || '{}'} onChange={e => setConfigs(old => ({...old, [p.id]:e.target.value}))}/></label></details><button className="secondary-button" disabled={busy === p.id} onClick={() => void toggle(p)}>{p.enabled ? 'Disable skill' : 'Review and enable'}</button></>}</article>)}
    {routines.length > 0 && <><h3>Learned routines</h3><p className="muted">Multi-step sequences the agent drafted from something it already did for you. A routine only runs when you approve it here, and it re-checks its own risky steps every time it's used.</p>
      {pendingRoutines.map(r => <article className="job-card" key={r.id}><div className="job-heading"><h3>{r.name}</h3><span className="status-label warning">pending approval</span></div><p>{r.description}</p>
        <div className="action-row"><button className="primary-button" disabled={busy === r.id} onClick={() => void decideRoutine(r.id, true)}>Approve</button><button className="secondary-button" disabled={busy === r.id} onClick={() => void decideRoutine(r.id, false)}>Reject</button></div></article>)}
      {activeRoutines.map(r => <article className="skill-card" key={r.id}><div><h3>{r.name}</h3><p>{r.description}</p><span className="micro-tag">USED {r.uses}×</span></div><button className="text-button" disabled={busy === r.id} onClick={() => void forgetRoutine(r.id)}>Forget</button></article>)}
    </>}
    <h3>Registered tools</h3>{catalog.map(t => <article className="skill-card" key={t.name}><div><h3>{t.name}</h3><p>{t.description}</p><span className="micro-tag">{['SAFE READ','NORMAL ACTION','APPROVAL REQUIRED','EXPLICIT APPROVAL REQUIRED'][t.permission_level]}</span></div></article>)}
  </div>;
}
