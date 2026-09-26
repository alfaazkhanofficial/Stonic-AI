import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api, type VoiceDevices, type VoiceStatus, type SettingValue } from '../api';

export function VoiceSettings({ draft, onPick, onChanged }: {
  draft: Record<string, SettingValue>; onPick: (key: string, value: string) => void; onChanged: () => void;
}) {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [devices, setDevices] = useState<VoiceDevices | null>(null);
  const [key, setKey] = useState(''), [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const load = () => { api<VoiceStatus>('/voice/status').then(setStatus).catch(() => {}); api<VoiceDevices>('/voice/devices').then(setDevices).catch(() => {}); };
  useEffect(load, []);

  async function save() {
    setBusy(true); setMessage('');
    try { await api('/voice/credential', { method: 'PUT', body: JSON.stringify({ key }) }); setKey(''); setMessage('Gemini key saved securely.'); load(); onChanged(); }
    catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!window.confirm('Remove the saved Gemini key from STONIC?')) return;
    setBusy(true);
    try { await api('/voice/credential', { method: 'DELETE', headers: { 'X-Stonic-Confirm': 'delete' } }); setMessage('Saved Gemini key removed. An environment key, if any, remains available.'); load(); onChanged(); }
    catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }
  const picker = (label: string, settingKey: string, names: string[]) => <div className="setting-field">
    <div className="setting-label"><label>{label} devices found</label></div>
    <div className="device-picks">
      <button type="button" className={!draft[settingKey] ? 'picked' : ''} onClick={() => onPick(settingKey, '')}>System default</button>
      {names.map(name => <button type="button" key={name} className={draft[settingKey] === name ? 'picked' : ''} onClick={() => onPick(settingKey, name)}>{name}</button>)}
    </div></div>;

  return <>
    <p className="voice-note">While voice is on, your microphone audio is streamed to Google's Gemini Live to hear and speak. Requests still run on this PC through STONIC's normal planner, verification and approvals. Actions that need approval can only be approved in Task activity, never by voice. Changes to the voice, model, devices and pause length apply the next time voice starts.</p>
    <div className="credential-field"><label htmlFor="voice-key">Gemini API key</label>
      <p>{status?.credential_configured ? 'A key is configured.' : 'Create a key at aistudio.google.com/apikey.'} It is encrypted for your Windows account, kept separate from your intelligence provider key, and excluded from settings exports.</p>
      <input id="voice-key" type="password" autoComplete="off" spellCheck={false} value={key} onChange={event => setKey(event.target.value)} placeholder="Gemini API key"/>
      <div className="action-row"><button className="secondary-button" disabled={busy || !key.trim()} onClick={() => void save()}>Save Gemini key</button>
        <button className="text-button" disabled={busy || !status?.credential_configured} onClick={() => void remove()}>Remove saved key</button></div>
      {message && <p role="status">{message}</p>}
    </div>
    {devices?.available === false ? <p className="voice-note">{devices.reason}</p> : <>
      {picker('Microphone', 'voice_input_device', devices?.input ?? [])}
      {picker('Speaker', 'voice_output_device', devices?.output ?? [])}
      <button className="text-button" onClick={load}>Refresh devices <RefreshCw size={12}/></button>
      <p className="voice-note">Pick a device, then Save changes. The Microphone and Speaker fields above hold the same value.</p></>}
    {status?.echo ? <p className="voice-note">Echo learning: {status.echo.calibrated ? (status.echo.reliable ? 'this room is judged reliably, so interrupting by voice can be trusted.' : 'echo and voices look too alike here, so interrupting by voice stays off.') : 'still listening to how your speakers sound in this room.'}</p> : null}
  </>;
}
