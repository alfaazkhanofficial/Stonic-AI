import { useEffect, useState } from 'react';
import { api } from '../api';
import { useUnsavedChanges } from './Unsaved';
interface Rule {id:string; name:string; kind:string; target:string; threshold:number; cooldown_seconds:number; enabled:boolean; last_fired?:string}
export function Events() {
  const [rules,setRules] = useState<Rule[]>([]), [name,setName] = useState(''), [kind,setKind] = useState('task_completed'), [target,setTarget] = useState('');
  const [error,setError] = useState(''), [busy,setBusy] = useState(false);
  useUnsavedChanges(!!name.trim()||!!target.trim());
  async function refresh() {setRules(await api<Rule[]>('/triggers'));}
  useEffect(() => {void refresh().catch(e => setError(e.message));}, []);
  async function create(e:React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {await api('/triggers',{method:'POST',body:JSON.stringify({name,kind,target,threshold:90,cooldown_seconds:600,enabled:true})}); setName('');setTarget('');await refresh();}
    catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function toggle(rule:Rule) {try {const {id,last_fired,...values}=rule; void last_fired; await api(`/triggers/${id}`,{method:'PATCH',body:JSON.stringify({...values,enabled:!values.enabled})});await refresh();} catch(e) {setError((e as Error).message);}}
  async function remove(rule:Rule) {if(!window.confirm(`Delete the “${rule.name}” notification rule?`))return;try{await api(`/triggers/${rule.id}`,{method:'DELETE',headers:{'X-Stonic-Confirm':'delete'}});await refresh();}catch(e){setError((e as Error).message);}}
  return <section className="domain-content"><h3>Events & proactive notices</h3><p className="muted">Rules send notices only when Proactive system notices is enabled in Configuration. Quiet hours and gaming mode apply. Each rule waits at least ten minutes between notices.</p>{error && <p role="alert" className="error-box">{error}</p>}
    <form onSubmit={e => void create(e)} className="reminder-form"><label>Notification name<input required maxLength={200} value={name} onChange={e=>setName(e.target.value)}/></label><label>When<select value={kind} onChange={e=>setKind(e.target.value)}>{[['task_completed','A task completes'],['application_opened','An application opens'],['file_created','A new file appears'],['network_restored','A network interface reconnects'],['high_cpu','CPU exceeds 90%'],['high_memory','Memory exceeds 90%']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>{['file_created','application_opened'].includes(kind)&&<label>{kind==='file_created'?'Folder path':'Executable name'}<input required value={target} maxLength={1000} onChange={e=>setTarget(e.target.value)} placeholder={kind==='file_created'?'C:\\Users\\you\\Downloads':'notepad.exe'}/></label>}<button className="primary-button" disabled={busy}>Save rule</button></form>
    {!rules.length&&<p className="muted">No custom notification rules.</p>}{rules.map(r=><article className="job-card" key={r.id}><h3>{r.name}</h3><p>{r.kind.replaceAll('_',' ')} {r.target&&`· ${r.target}`}</p><span className="micro-tag">{r.enabled?'ENABLED':'DISABLED'}</span><div className="action-row"><button className="text-button" onClick={()=>void toggle(r)}>{r.enabled?'Disable':'Enable'}</button><button className="text-button" onClick={()=>void remove(r)}>Delete rule</button></div></article>)}
  </section>;
}
