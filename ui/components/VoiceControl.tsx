import { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, MicOff, Square } from 'lucide-react';
import { api, type VoiceStatus } from '../api';
import { voiceStore } from '../voiceStore';
import '../voice.css';

const LABELS: Record<string, string> = {
  off: 'Voice off', connecting: 'Connecting', listening: 'Listening', thinking: 'Working', speaking: 'Speaking',
  muted: 'Muted', standby: 'Push to talk', reconnecting: 'Reconnecting', error: 'Voice error',
};

export function VoiceControl({ session, onSettings, onNotice }: {
  session: string; onSettings: (category: string) => void; onNotice: (message: string) => void;
}) {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [held, setHeld] = useState(false);
  const heldRef = useRef(false);

  useEffect(() => {
    let alive = true;
    api<VoiceStatus>('/voice/status').then(next => { if (alive) { setStatus(next); voiceStore.set({ state: next.state }); } }).catch(() => {});
    const source = new EventSource('/api/voice/stream');
    source.onmessage = event => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'state') { setStatus(data as VoiceStatus); voiceStore.set({ state: data.state }); }
        else if (data.type === 'level') voiceStore.set({ levelIn: Number(data.in) || 0, levelOut: Number(data.out) || 0 });
      } catch { /* a malformed frame is skipped; the next state frame corrects the view */ }
    };
    return () => { alive = false; source.close(); voiceStore.set({ state: 'off', levelIn: 0, levelOut: 0 }); };
  }, []);

  // Voice speaks into whichever conversation is open.
  useEffect(() => {
    if (status?.running && status.session_id !== session) api('/voice/session', { method: 'PUT', body: JSON.stringify({ session_id: session }) }).catch(() => {});
  }, [session, status?.running, status?.session_id]);

  const post = useCallback(async (path: string, body: unknown = {}) => {
    try { setStatus(await api<VoiceStatus>(path, { method: 'POST', body: JSON.stringify(body) })); return true; }
    catch (error) { onNotice((error as Error).message); return false; }
  }, [onNotice]);

  async function toggle() {
    if (busy) return;
    setBusy(true);
    try {
      if (status?.running) { await post('/voice/stop'); return; }
      if (status && !status.consent) {
        if (!window.confirm("Voice streams your microphone to Google's Gemini Live while it is on, and nothing while it is off or muted. STONIC's actions still run on this PC through its normal approvals. Allow cloud voice?")) return;
        await api('/config', { method: 'PATCH', body: JSON.stringify({ voice_cloud_consent: true }) });
      }
      if (status && !status.credential_configured) { onSettings('Voice'); onNotice('Add a Gemini API key in Settings → Voice, then press the microphone again.'); return; }
      await post('/voice/start', { session_id: session });
    } catch (error) { onNotice((error as Error).message); }
    finally { setBusy(false); }
  }

  const releaseHold = useCallback(() => {
    if (!heldRef.current) return;
    heldRef.current = false; setHeld(false);
    void post('/voice/ptt', { held: false });
  }, [post]);
  useEffect(() => { window.addEventListener('blur', releaseHold); return () => window.removeEventListener('blur', releaseHold); }, [releaseHold]);

  const state = status?.state ?? 'off';
  const running = Boolean(status?.running);
  const live = running && ['listening', 'speaking', 'thinking'].includes(state);
  const busyTalking = state === 'speaking' || state === 'thinking';
  return <span className="voice-control">
    <button type="button" className={`icon-button ${running ? 'selected' : ''} ${state === 'error' ? 'voice-error' : ''}`} disabled={busy || !status}
      aria-label={running ? 'Turn voice off' : 'Turn voice on'} aria-pressed={running} title={status?.detail || (running ? 'Turn voice off' : 'Turn voice on')} onClick={() => void toggle()}>
      <Mic size={16} className={live ? 'voice-dot-live' : undefined}/>
    </button>
    {running ? <button type="button" className={`icon-button ${status?.muted ? 'selected' : ''}`} aria-label={status?.muted ? 'Unmute microphone' : 'Mute microphone'} aria-pressed={Boolean(status?.muted)}
      title={status?.muted ? 'Unmute microphone' : 'Mute microphone (closes the device)'} onClick={() => void post('/voice/mute', { muted: !status?.muted })}>
      {status?.muted ? <MicOff size={15}/> : <Mic size={15} strokeWidth={1.2}/>}</button> : null}
    {running && busyTalking ? <button type="button" className="icon-button" aria-label="Stop speaking" title="Stop speaking" onClick={() => void post('/voice/interrupt')}><Square size={13}/></button> : null}
    {running && status?.push_to_talk !== 'off' ? <button type="button" className={`voice-hold ${held ? 'held' : ''}`} aria-label="Hold to talk"
      onPointerDown={event => { event.currentTarget.setPointerCapture(event.pointerId); heldRef.current = true; setHeld(true); void post('/voice/ptt', { held: true }); }}
      onPointerUp={releaseHold} onPointerCancel={releaseHold}>{held ? 'TALKING' : 'HOLD'}</button> : null}
    <span className={`voice-status ${live ? 'live' : state === 'error' || state === 'reconnecting' ? 'warn' : ''}`} role="status" aria-live="polite">{LABELS[state] ?? state}</span>
  </span>;
}
