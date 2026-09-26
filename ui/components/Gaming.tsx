import { useEffect, useState } from 'react';
import { api } from '../api';
import { TaskActivity } from './TaskActivity';
interface GamingState {steam_installed:boolean; games:{app_id:string;name:string}[]; game_processes:{pid:number;name:string;memory_mb:number;start_time:number}[]; gaming_mode:boolean; fps_available:boolean; fps_detail:string; system:{cpu_percent:number;memory_percent:number}}
export function Gaming() {
  const [data,setData] = useState<GamingState|null>(null), [error,setError] = useState(''), [busy,setBusy] = useState(false);
  async function refresh() {setData(await api<GamingState>('/gaming'));}
  useEffect(()=>{void refresh().catch(e=>setError(e.message));},[]);
  async function action(tool:string,args:Record<string,unknown>) {setBusy(true);setError('');try{await api('/computer/action',{method:'POST',body:JSON.stringify({tool,arguments:args})});await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <div className="domain-content">{error&&<p className="error-box" role="alert">{error}</p>}<div className="action-row"><button className="secondary-button" disabled={!data||busy} onClick={()=>void action('gaming.mode',{enabled:!data?.gaming_mode})}>{data?.gaming_mode?'Leave gaming mode':'Enable gaming mode'}</button><button className="text-button" onClick={()=>void refresh().catch(e=>setError(e.message))}>Refresh games</button></div><p className="muted">Gaming mode keeps proactive notices quiet. FPS comes from measured presentation events.</p>
    {data&&<><h3>Current session</h3><p>CPU {data.system.cpu_percent}% · Memory {data.system.memory_percent}%</p>{!data.game_processes.length&&<p className="muted">No running game matched the installed Steam library.</p>}{data.game_processes.map(p=><article className="job-card" key={p.pid}><h3>{p.name}</h3><p>{p.memory_mb} MB memory</p><button className="secondary-button" disabled={busy||!data.fps_available} onClick={()=>void action('gaming.fps',{pid:p.pid,expected_start_time:p.start_time,seconds:5})}>Measure FPS for 5 seconds</button></article>)}<h3>Installed games</h3>{!data.steam_installed&&<p className="muted">Steam is not installed. You can still use computer control and approved screen analysis for other games.</p>}{data.games.map(g=><article className="job-card" key={g.app_id}><h3>{g.name}</h3><button className="text-button" disabled={busy} onClick={()=>void action('gaming.launch',{app_id:g.app_id,expected_name:g.name})}>Launch game</button></article>)}</>}
    <TaskActivity/>
  </div>;
}
