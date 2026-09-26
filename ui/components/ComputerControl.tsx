import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { TaskActivity } from './TaskActivity';
interface DesktopWindow {hwnd: number; pid: number; title: string; bounds: {left: number; top: number; right: number; bottom: number}}

export function ComputerControl() {
  const [windows, setWindows] = useState<DesktopWindow[]>([]), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {try {const result = await api<{windows: DesktopWindow[]}>('/computer/windows'); setWindows(result.windows);} catch(e) {setError((e as Error).message);}}, []);
  useEffect(() => {void refresh();}, [refresh]);
  async function action(tool: string, args: object) {
    setBusy(true); setError('');
    try {await api('/computer/action', {method:'POST', body:JSON.stringify({tool, arguments:args})}); await refresh();}
    catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  return <div className="domain-content"><p className="muted">Choose an observed window or launch an installed app. Sensitive actions appear below for review before execution.</p>{error && <p role="alert" className="error-box">{error}</p>}
    <div className="action-row">{['notepad','calculator','explorer','edge','chrome'].map(app => <button key={app} className="secondary-button" disabled={busy} onClick={() => void action('computer.launch', {app})}>Open {app}</button>)}<button className="text-button" onClick={() => void refresh()}>Refresh windows</button></div>
    <div className="domain-list">{windows.map(w => <article key={w.hwnd}><div><strong>{w.title}</strong><p>{w.bounds.right - w.bounds.left} × {w.bounds.bottom - w.bounds.top}</p></div><div className="action-row">{['focus','minimize','maximize','close'].map(name => <button key={name} className="text-button" disabled={busy} onClick={() => void action('computer.window', {hwnd:w.hwnd, expected_pid:w.pid, expected_title:w.title, action:name})}>{name}</button>)}</div></article>)}</div><TaskActivity onChange={() => void refresh()}/>
  </div>;
}
