import { useEffect, useRef, useState } from 'react';
import { Settings2, SlidersHorizontal, Palette, UserRound, ShieldCheck, Download, Upload, RotateCcw, ArrowUpRight, Mic, Bot } from 'lucide-react';
import { api, type ConfigResponse, type SettingValue, type HealthCheck } from '../api';
import { Modal } from './PanelFrame';
import { Credentials } from './Credentials';
import { Preferences } from './Preferences';
import { VoiceSettings } from './VoiceSettings';
import { confirmDiscard, useUnsavedChanges } from './Unsaved';

export function SettingsPanel({ initialCategory, onClose, onSaved }: {initialCategory?: string; onClose: () => void; onSaved: () => void}) {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [draft, setDraft] = useState<Record<string, SettingValue>>({});
  const [category, setCategory] = useState(initialCategory || 'AI & Providers');
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [preferenceDirty,setPreferenceDirty]=useState(false);
  function selectCategory(next:string){if(next!==category&&preferenceDirty&&!window.confirm('Discard the unsaved preference before changing categories?'))return;setCategory(next);}
  const [search, setSearch] = useState('');
  const upload = useRef<HTMLInputElement>(null);
  useEffect(() => { api<ConfigResponse>('/config').then(c => { setConfig(c); setDraft(c.values); }).catch(e => setError(e.message)); }, []);
  const dirty = JSON.stringify(config?.values) !== JSON.stringify(draft);
  useUnsavedChanges(!!config&&dirty,'Configuration');
  function close() { if(confirmDiscard('Configuration'))onClose(); }
  async function save() {
    setBusy(true); setError(''); setNotice('');
    try {
      const values = await api<Record<string, SettingValue>>('/config', { method: 'PATCH', body: JSON.stringify(draft) });
      const restart = Object.entries(config?.schema.properties || {}).some(([key, field]) => field.restart_required && config?.values[key] !== values[key]);
      const fresh = await api<ConfigResponse>('/config');
      setDraft(fresh.values); setConfig(fresh); setNotice(restart ? 'Saved. Restart STONIC to apply the changed setting.' : 'Saved. Changes are active now.'); onSaved();
    } catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function test() {
    setBusy(true); setNotice(''); setError('');
    try { const check = await api<HealthCheck>('/provider/test', { method: 'POST' }); setNotice(check.detail); onSaved(); }
    catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function exportConfig() {
    const blob = new Blob([JSON.stringify(config?.values, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'stonic-settings.json'; a.click(); URL.revokeObjectURL(url);
  }
  async function importConfig(file?: File) {
    if (!file) return;
    try {
      if (file.size > 50000) throw new Error('Configuration files must be smaller than 50 KB.');
      const values = JSON.parse(await file.text());
      if (!values || typeof values !== 'object' || Array.isArray(values)) throw new Error('Choose a valid STONIC settings object.');
      for (const key of Object.keys(values)) if (!config?.schema.properties[key]) throw new Error(`Unsupported setting: ${key}`);
      // Consent to stream audio to a cloud service must be given on this PC, by the person using it, never by a file.
      const held = ['voice_cloud_consent', 'voice_autostart'].filter(key => key in values); held.forEach(key => delete values[key]);
      setDraft({ ...draft, ...values }); setNotice(held.length ? 'Imported for review. Cloud voice consent and auto-start are never imported; set them yourself. Save to validate and apply.' : 'Imported for review. Save to validate and apply.');
    } catch(e) { setError((e as Error).message); }
  }
  const categories = [ ['AI & Providers', SlidersHorizontal], ['Agent', Bot], ['Appearance', Palette], ['Personalization', UserRound], ['Privacy', ShieldCheck], ['Memory', SlidersHorizontal], ['Tasks & Automation', SlidersHorizontal], ['Computer Control', SlidersHorizontal], ['Events & Proactive', SlidersHorizontal], ['Gaming', SlidersHorizontal], ['Voice', Mic] ] as const;
  function resetCategory(all = false) {
    if (!config || !window.confirm(all ? 'Restore every setting to its default? Your API key and records are kept.' : `Restore ${category} settings to defaults?`)) return;
    const updates = Object.fromEntries(Object.entries(config.schema.properties).filter(([, f]) => !f.internal && (all || f.category === category)).map(([key, f]) => [key, f.default as SettingValue]));
    setDraft(old => ({...old, ...updates})); setNotice('Defaults restored in the form. Save to apply.');
  }
  return <Modal title="Configuration" subtitle="Make this workspace yours." onClose={close} wide>
    <div className="settings-layout"><nav className="settings-nav" aria-label="Configuration categories">{categories.map(([name, Icon]) => <button key={name} className={category === name ? 'selected' : ''} onClick={() => selectCategory(name)}><Icon size={16}/><span>{name}</span>{category === name ? <span className="nav-dot"/> : null}</button>)}<div className="settings-local"><ShieldCheck size={16}/><span>Saved locally.<br/>Always in your control.</span></div></nav>
      <div className="settings-fields"><div className="section-heading"><h3>{category}</h3><span className="micro-tag">LIVE SETTINGS</span></div>
      {error ? <div role="alert" className="error-box">{error}</div> : null}{notice ? <div role="status" className="notice-box">{notice}</div> : null}
      <input aria-label="Search configuration" placeholder="Search all settings…" value={search} onChange={e => setSearch(e.target.value)}/>
      {!config ? <p className="loading-text">Loading configuration…</p> : <>
        {Object.entries(config.schema.properties).filter(([, field]) => !field.internal && (search ? `${field.title} ${field.help} ${field.category}`.toLowerCase().includes(search.toLowerCase()) : field.category === category)).map(([key, field]) => <div className="setting-field" key={key}>
          <div className="setting-label"><label htmlFor={`config-${key}`}>{field.title}</label><button className="icon-button" title={`Reset ${field.title}`} aria-label={`Reset ${field.title}`} onClick={() => { setDraft({ ...draft, [key]: field.default as SettingValue }); setNotice('Default restored in the form. Save to apply.'); }}><RotateCcw size={12}/></button></div>
          {field.type === 'boolean' ? <label className="checkbox-line"><input id={`config-${key}`} type="checkbox" checked={Boolean(draft[key])} onChange={e => setDraft({...draft, [key]: e.target.checked})}/><span>{draft[key] ? 'Enabled' : 'Disabled'}</span></label> : field.enum ? <select id={`config-${key}`} value={String(draft[key])} onChange={e => setDraft({...draft, [key]: e.target.value})}>{field.enum.map(option => <option key={option} value={option}>{option.charAt(0).toUpperCase() + option.slice(1)}</option>)}</select> : <input id={`config-${key}`} type={['number','integer'].includes(field.type) ? 'number' : 'text'} min={field.minimum} max={field.maximum} maxLength={field.maxLength} step={field.type === 'integer' ? 1 : field.type === 'number' ? .1 : undefined} value={String(draft[key] ?? '')} onChange={e => setDraft({...draft, [key]: ['number','integer'].includes(field.type) ? Number(e.target.value) : e.target.value})}/>} 
          <p>{field.help}{field.restart_required ? ' Save, then restart STONIC to apply.' : ''}</p>
        </div>)}
        {category === 'AI & Providers' ? <><Credentials endpoint={String(config.values.llm_base_url || '')} configured={config.credential_configured} onSaved={() => {api<ConfigResponse>('/config').then(c => {setConfig(c); setDraft(c.values);}).catch(e => setError(e.message)); onSaved();}}/><button className="text-button" disabled={busy || dirty} onClick={() => void test()}>Test saved connection <ArrowUpRight size={13}/></button>{dirty ? <small>Save changes before testing.</small> : null}</> : null}
        {category === 'Voice' && !search ? <VoiceSettings draft={draft} onPick={(key, value) => setDraft(old => ({...old, [key]: value}))} onChanged={onSaved}/> : null}
        {category === 'Personalization' && !search ? <Preferences onDirtyChange={setPreferenceDirty}/> : null}
        <div className="action-row"><button className="text-button" onClick={() => resetCategory()}>Reset category</button><button className="text-button" onClick={() => resetCategory(true)}>Reset all settings</button></div>
      </>}
      </div>
    </div>
    <footer className="settings-footer"><div className="settings-transfer"><button className="icon-button" title="Export saved settings" aria-label="Export saved settings" disabled={!config} onClick={exportConfig}><Download size={16}/></button><button className="icon-button" title="Import settings" aria-label="Import settings" disabled={!config} onClick={() => upload.current?.click()}><Upload size={16}/></button><input ref={upload} type="file" accept="application/json,.json" hidden onChange={e => { void importConfig(e.target.files?.[0]); e.target.value = ''; }}/><span>Secrets never exported</span></div><button className="primary-button" onClick={() => void save()} disabled={!config || busy || !dirty}><Settings2 size={14}/>{busy ? 'Working…' : 'Save changes'}</button></footer>
  </Modal>;
}
