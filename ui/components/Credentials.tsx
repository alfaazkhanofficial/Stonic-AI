import { useState } from 'react';
import { api } from '../api';

export function Credentials({ configured, onSaved, endpoint }: { configured: boolean; onSaved: () => void; endpoint: string }) {
  const isXkiro = (() => { try { return new URL(endpoint).hostname === 'api.xkiro.com'; } catch { return false; } })();
  const providerName = isXkiro ? 'xKiro' : 'provider';
  const [key, setKey] = useState(''), [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  async function save() {
    setBusy(true); setMessage('');
    try {
      await api('/provider/credential', {method: 'PUT', body: JSON.stringify({key})});
      setKey(''); setMessage(`${providerName} key saved securely. Test the connection below.`); onSaved();
    } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!window.confirm(`Remove the saved ${providerName} key from STONIC?`)) return;
    setBusy(true);
    try { await api('/provider/credential', {method: 'DELETE', headers: {'X-Stonic-Confirm': 'delete'}}); setMessage('Saved provider key removed. Environment fallback keys, if any, remain available.'); onSaved(); }
    catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="credential-field"><label htmlFor="provider-key">{isXkiro ? "xKiro API key" : "Provider API key"}</label>
    <p>{configured ? 'A key is configured.' : 'Enter a key if this endpoint requires authentication.'} It is encrypted for your Windows account and excluded from settings exports.</p>
    <input id="provider-key" type="password" autoComplete="off" spellCheck={false} value={key} onChange={e => setKey(e.target.value)} placeholder="API key"/>
    <div className="action-row"><button className="secondary-button" disabled={busy || !key.trim()} onClick={() => void save()}>Save provider key</button><button className="text-button" disabled={busy || !configured} onClick={() => void remove()}>Remove saved key</button></div>
    {message && <p role="status">{message}</p>}
  </div>;
}
