import { useCallback, useEffect, useRef, useState, type SetStateAction } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, ArrowUp, ArrowUpRight, BookOpen, Bot, Brain, Camera, Check, ChevronRight, CircleHelp, Command, Cpu, Database, Ellipsis, Expand, FileImage, Fingerprint, GitBranch, HardDrive, ImagePlus, Layers3, ListTodo, LoaderCircle, Maximize2, Minus, Monitor, Network, NotebookPen, Plus, Radio, RefreshCw, Search, Settings2, ShieldCheck, Sparkles, Square, Trash2, Workflow, X, Zap } from 'lucide-react';
import { api, type ConfigResponse, type LogEvent, type Message, type Skill, type Status } from './api';
import { Modal, PanelLayoutContext } from './components/PanelFrame';
import { Orb } from './components/Orb';
import { Records } from './components/Records';
import { SettingsPanel } from './components/Settings';
import { TaskActivity } from './components/TaskActivity';
import { Productivity } from './components/Productivity';
import { Research } from './components/Research';
import { ComputerControl } from './components/ComputerControl';
import { VisionPanel } from './components/VisionPanel';
import { Skills } from './components/Skills';
import { Gaming } from './components/Gaming';
import { confirmDiscard } from './components/Unsaved';
import { FirstRun } from './components/FirstRun';
import { VoiceControl } from './components/VoiceControl';
import { SystemMonitor } from './components/SystemMonitor';
import './activity.css';

type Tab = 'chats'|'logs'|'notes'|'tasks';
type Panel = 'settings'|'memory'|'skills'|'diagnostics'|'permissions'|'commands'|'visual'|'flow'|'activity'|'productivity'|'research'|'vision'|'gaming'|'system'|null;
const PANEL_TITLES:Record<string,string>={settings:'Configuration',memory:'Memory',skills:'Skills & capabilities',diagnostics:'System diagnostics',permissions:'Computer control',visual:'Visual hub',activity:'Task activity',productivity:'Reminders & notifications',research:'Web intelligence',vision:'Visual intelligence',gaming:'Gaming intelligence',system:'System monitor'};

function BrandMark({small = false}: {small?: boolean}) {
  return <div className={`brand-mark ${small ? 'brand-small' : ''}`}><svg viewBox="0 0 30 30" fill="none" aria-hidden="true"><path d="M8 9h15L8 21h15M6 15h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg></div>;
}

function App() {
  const [firstRun,setFirstRun]=useState(()=>!!window.stonicDesktop&&!localStorage.getItem('stonic.onboarded'));
  function finishSetup(){localStorage.setItem('stonic.onboarded','1');setFirstRun(false);}
  const [status, setStatus] = useState<Status | null>(null);
  const [connected, setConnected] = useState(false);
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [samples, setSamples] = useState<number[]>([]);
  const [tab, setTabRaw] = useState<Tab>('chats');
  const dirtyRecords = useRef<Record<string, boolean>>({});
  const trackDirty = useCallback((kind: string, dirty: boolean) => { dirtyRecords.current[kind] = dirty; }, []);
  function setTab(next: Tab) {
    if (next !== tab && dirtyRecords.current[tab] && !window.confirm('Discard the unsaved record before changing tabs?')) return false;
    setTabRaw(next); return true;
  }
  const [panel, setPanelRaw] = useState<Panel>(null);
  const panelRef=useRef<Panel>(panel);panelRef.current=panel;
  const [pinned,setPinned]=useState<string[]>(()=>{try {const saved=JSON.parse(localStorage.getItem('stonic.pinned-panels')||'[]');return Array.isArray(saved)?saved.filter(p=>typeof p==='string'&&PANEL_TITLES[p]).slice(0,4):[];}catch{return [];}});
  const pinnedRef=useRef(pinned);pinnedRef.current=pinned;
  function setPanel(value:SetStateAction<Panel>){const current=panelRef.current,next=typeof value==='function'?value(current):value;if(current!==next&&current&&!pinnedRef.current.includes(current)&&!confirmDiscard(PANEL_TITLES[current]||current))return;panelRef.current=next;setPanelRaw(next);}
  function pinPanel(title:string,value:boolean){const key=Object.keys(PANEL_TITLES).find(p=>PANEL_TITLES[p]===title);if(!key)return;if(value&&!pinnedRef.current.includes(key)&&pinnedRef.current.length>=4){setToast('Four panels are pinned. Unpin one before adding another.');return;}if(!value&&panelRef.current!==key&&!confirmDiscard(title))return;setPinned(old=>{const next=value?[...old.filter(p=>p!==key),key]:old.filter(p=>p!==key);localStorage.setItem('stonic.pinned-panels',JSON.stringify(next));return next;});}
  function closePanel(key:Panel){if(key)pinPanel(PANEL_TITLES[key],false);setPanel(current=>current===key?null:current);}
  function visible(key:Panel){return panel===key||!!key&&pinned.includes(key);}
  const [category, setCategory] = useState('AI & Providers');
  const [session, setSession] = useState(() => localStorage.getItem('stonic.session') || 'main');
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingText,setStreamingText]=useState('');
  const [input, setInput] = useState(''), [sending, setSending] = useState(false);
  const [toast, setToast] = useState('');
  const [skills, setSkills] = useState<Skill[]>([]);
  const [commandQuery, setCommandQuery] = useState('');
  const [imageUrl, setImageUrl] = useState(''), [imageName, setImageName] = useState('');
  const [flow, setFlow] = useState<string[]>([]), [flowDraft, setFlowDraft] = useState('');
  const [camera, setCamera] = useState(false);
  const cameraStream = useRef<MediaStream | null>(null);
  const cameraVideo = useRef<HTMLVideoElement>(null);
  const upload = useRef<HTMLInputElement>(null);
  const chatEnd = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const currentSession = useRef(session);
  currentSession.current = session;
  const clock = new Date();
  const providerCheck = status?.checks.find(c => c.id === 'llm');
  const providerConfigured = Boolean(config?.values.llm_model && (config?.credential_configured || !config?.credential_required));
  const aiReady = connected && providerCheck?.status === 'ready';
  const providerStatusLabel = aiReady ? 'CONNECTED' : providerConfigured ? 'PROVIDER ISSUE' : 'PROVIDER SETUP';
  const providerActionLabel = aiReady ? 'START A CONVERSATION' : providerConfigured ? 'CHECK PROVIDER' : 'CONNECT AI';
  const providerSummary = aiReady ? 'Intelligence available' : providerConfigured ? (providerCheck?.detail || 'Your provider configuration is saved but currently needs attention.') : 'Your workspace, ready when you are';
  const reduced = Boolean(config?.values.reduced_motion) || matchMedia('(prefers-reduced-motion: reduce)').matches;

  const refresh = useCallback(async () => {
    try {
      const next = await api<Status>('/status'); setStatus(next); setConnected(true);
      setSamples(points => [...points.slice(-39), next.metrics.cpu_percent]);
    } catch { setConnected(false); }
  }, []);
  const reloadConfig = useCallback(async () => {
    try { setConfig(await api<ConfigResponse>('/config')); await refresh(); }
    catch (e) { setToast((e as Error).message); }
  }, [refresh]);

  useEffect(() => {
    void refresh(); void reloadConfig();
    api<LogEvent[]>('/logs').then(setLogs).catch(() => {});
    const timer = window.setInterval(() => { void refresh(); }, 2000);
    const events = new EventSource('/api/events');
    const removeBackendListener=window.stonicDesktop?.onBackendStatus(data=>{setToast(data.message);if(data.state==='connected')void refresh();else setConnected(false);});
    events.onmessage = event => {
      try {
        const entry = JSON.parse(event.data) as LogEvent;
        if (entry.id && entry.message) setLogs(old => [entry, ...old.filter(e => e.id !== entry.id)].slice(0, 80));
      } catch { setToast('A diagnostic event could not be read.'); }
    };
    events.onopen = () => { api<LogEvent[]>('/logs').then(setLogs).catch(() => {}); };
    events.addEventListener('conversation', () => {api<Message[]>(`/chat/${currentSession.current}`).then(setMessages).catch(e => setToast(e.message));});
    events.addEventListener('panel',event=>{try{const target=JSON.parse((event as MessageEvent).data).panel;if(!panelRef.current&&PANEL_TITLES[target])setPanel(target as Panel);}catch{/* Domain activity remains accessible through Commands. */}});
    events.addEventListener('generation',event=>{try{const data=JSON.parse((event as MessageEvent).data);if(data.session_id!==currentSession.current)return;if(data.phase==='start')setStreamingText('');else if(data.phase==='delta')setStreamingText(old=>old+data.text);}catch{/* A final persisted message replaces incomplete transient output. */}});
    events.addEventListener('notification', event => {try {const notice=JSON.parse((event as MessageEvent).data); if(notice.quiet)return; setToast(`${notice.title}: ${notice.body}`);window.stonicDesktop?.notify(notice);} catch { /* The persisted inbox retains the notification. */ }});
    return () => { clearInterval(timer); events.close();removeBackendListener?.(); cameraStream.current?.getTracks().forEach(t => t.stop()); };
  }, [refresh, reloadConfig]);
  useEffect(() => {
    localStorage.setItem('stonic.session', session);
    let current = true;
    api<Message[]>(`/chat/${session}`).then(data => { if(current) setMessages(data); }).catch(e => setToast(e.message));
    return () => { current = false; };
  }, [session]);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'end' }); }, [messages, sending, reduced]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 6500); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => {
    function keys(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPanel(p => p === 'commands' ? null : 'commands'); setCommandQuery(''); }
      if ((e.ctrlKey || e.metaKey) && e.key === ',') { e.preventDefault(); setCategory('AI & Providers'); setPanel('settings'); }
    }
    window.addEventListener('keydown', keys); return () => window.removeEventListener('keydown', keys);
  }, []);
  useEffect(() => { if (cameraVideo.current && cameraStream.current) cameraVideo.current.srcObject = cameraStream.current; }, [camera]);
  useEffect(() => () => { if (imageUrl.startsWith('blob:')) URL.revokeObjectURL(imageUrl); }, [imageUrl]);

  function settings(selected = 'AI & Providers') { setCategory(selected); setPanel('settings'); }
  function showTasks() { setTab('tasks'); setPanel(null); }
  async function send(text = input) {
    if (!text.trim() || sending || !connected) return;
    if (!setTab('chats')) return;
    setInput(''); setSending(true);
    const outgoing: Message = {id: crypto.randomUUID(), session_id: session, role:'user', content: text.trim(), created_at:new Date().toISOString()};
    setMessages(old => [...old, outgoing]);
    try { const response = await api<Message>('/chat', {method:'POST', body:JSON.stringify({content:text.trim(),session_id:session})}); setMessages(old => [...old, response]); setStreamingText(''); }
    catch(e) { setToast((e as Error).message); setInput(text); setStreamingText(''); setMessages(old => old.filter(m => m.id !== outgoing.id)); }
    finally { setSending(false); void refresh(); }
  }
  async function loadImage(file?: File) {
    if (!file) return;
    if (!['image/png','image/jpeg','image/webp','image/gif'].includes(file.type) || file.size > 20_000_000) { setToast('Choose a PNG, JPEG, WebP, or GIF image under 20 MB.'); return; }
    setImageUrl(URL.createObjectURL(file)); setImageName(file.name); setFlow([]); setToast('Image added locally. It has not been sent to an AI provider.');
  }
  async function captureScreen() {
    try {
      if (window.stonicDesktop) {
        const data = await window.stonicDesktop.captureScreen(); if (data) { setImageUrl(data); setImageName('Screen capture · local only'); setFlow([]); }
      } else {
        const stream = await navigator.mediaDevices.getDisplayMedia({video: true, audio: false});
        try {
          const video = document.createElement('video'); video.srcObject = stream; await video.play();
          await new Promise<void>(resolve => video.requestVideoFrameCallback(() => resolve()));
          const canvas = document.createElement('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
          canvas.getContext('2d')?.drawImage(video, 0, 0); setImageUrl(canvas.toDataURL('image/png')); setImageName('Screen capture · local only'); setFlow([]);
        } finally { stream.getTracks().forEach(t => t.stop()); }
      }
    } catch { setToast('Screen capture was cancelled or is unavailable. You can import an image instead.'); }
  }
  async function toggleCamera() {
    if (camera) { cameraStream.current?.getTracks().forEach(t => t.stop()); cameraStream.current = null; setCamera(false); return; }
    try { const stream = await navigator.mediaDevices.getUserMedia({video:true, audio:false}); cameraStream.current = stream; setCamera(true); stream.getVideoTracks()[0].onended = () => setCamera(false); }
    catch { setToast('Camera access is unavailable or was declined. No camera stream is active.'); }
  }
  function newChat() { if(sending || !setTab('chats')) return; setMessages([]); setSession(crypto.randomUUID()); inputRef.current?.focus(); }
  async function showSkills() { setPanel('skills'); try { setSkills(await api<Skill[]>('/skills')); } catch(e) { setToast((e as Error).message); } }

  const commands = [
    {name:'Open configuration', hint:'Settings and providers', action:() => settings()},
    {name:'Open memory', hint:'Your saved context', action:() => setPanel('memory')},
    {name:'Open notes', hint:'Capture a thought', action:() => {setPanel(null);setTab('notes');}},
    {name:'Open tasks', hint:'Plan what comes next', action:showTasks},
    {name:'Task activity and approvals', hint:'Review plans and verified actions', action:() => setPanel('activity')},
    {name:'Reminders and notifications', hint:'Timers, recurrence, calendar and notices', action:() => setPanel('productivity')},
    {name:'Web research', hint:'Quick search, research and deep research', action:() => setPanel('research')},
    {name:'Gaming intelligence', hint:'Game library, session context and measured FPS', action:() => setPanel('gaming')},
    {name:'Analyze visual hub image', hint:'Local OCR and approved image understanding', action:() => setPanel('vision')},
    {name:'System diagnostics', hint:'Real service health', action:() => setPanel('diagnostics')},
    {name:'Open system monitor',hint:'Live CPU, memory, disk and recent activity',action:()=>setPanel('system')},
    {name:'Show system status', hint:'Live CPU and memory', action:() => {setPanel(null);void send('/status');}},
    {name:'New conversation', hint:'Start a fresh context', action:() => {setPanel(null);newChat();}},
  ].filter(c => `${c.name} ${c.hint}`.toLowerCase().includes(commandQuery.toLowerCase()));

  const visualContent = imageUrl ? <div className="visual-image"><img src={imageUrl} alt={imageName}/><div className="image-caption"><FileImage size={13}/><span>{imageName}</span><span className="micro-tag">LOCAL</span></div></div> : flow.length ? <div className="flow-preview">{flow.map((step, i) => <div className="flow-item" key={`${i}-${step}`}><div><span>{String(i + 1).padStart(2, '0')}</span>{step}</div>{i < flow.length - 1 ? <ArrowDownToLine size={19}/> : null}</div>)}</div> : null;

  return <PanelLayoutContext.Provider value={{pinned:pinned.map(p=>PANEL_TITLES[p]),pin:pinPanel}}><div className={`app ${reduced ? 'reduced-motion' : ''} density-${config?.values.interface_density || 'comfortable'}`}>
    <header className="app-header"><div className="brand"><BrandMark/><span>STONIC<span className="brand-version">V2</span></span><span className="header-divider"/><span className="workspace-label">PERSONAL INTELLIGENCE</span></div><div className="header-right"><span className={`connection-indicator ${connected ? '' : 'offline'}`}><i/>{connected ? 'LOCAL WORKSPACE' : 'RECONNECTING'}</span><button className="command-trigger" aria-label="Open command palette" onClick={() => {setCommandQuery('');setPanel('commands');}}><Command size={13}/><span>Commands</span><kbd>Ctrl K</kbd></button>{window.stonicDesktop ? <div className="window-actions"><button aria-label="Minimize window" onClick={() => window.stonicDesktop?.windowAction('minimize')}><Minus size={15}/></button><button aria-label="Maximize or restore window" onClick={() => window.stonicDesktop?.windowAction('maximize')}><Square size={12}/></button><button className="window-close" aria-label="Close window" onClick={() => window.stonicDesktop?.windowAction('close')}><X size={16}/></button></div> : <span className="preview-badge">WEB PREVIEW</span>}</div></header>
    <main className="dashboard">
      <aside className="left-rail panel-surface">
        <section className="media-section"><div className="panel-heading"><span><Radio size={14}/> MEDIA LINK</span><button className="icon-button" aria-label="Media link information" onClick={() => setToast('Camera is a local preview. Screen capture and imported images stay in the Visual Hub until you close this workspace.')}><Ellipsis size={17}/></button></div>
          <div className={`media-view ${camera ? 'camera-live' : ''}`}>{camera ? <video ref={cameraVideo} autoPlay muted playsInline/> : <><div className="viewfinder-corner tl"/><div className="viewfinder-corner tr"/><div className="viewfinder-corner bl"/><div className="viewfinder-corner br"/><div className="media-reticle"><Camera size={26} strokeWidth={1}/><span>NO ACTIVE SOURCE</span></div><div className="media-grid"/></>}
          <div className="media-controls"><span className={`micro-tag ${camera ? 'online' : ''}`}><i/>{camera ? 'CAMERA LIVE' : 'STANDBY'}</span><div><button className={`icon-button ${camera ? 'selected' : ''}`} aria-label={camera ? 'Stop camera preview' : 'Open camera preview'} onClick={() => void toggleCamera()}><Camera size={15}/></button><button className="icon-button" aria-label="Capture screen" onClick={() => void captureScreen()}><Monitor size={15}/></button></div></div></div>
        </section>
        <section className="system-feed"><div className="panel-heading"><span><Activity size={13}/> SYSTEM FEED</span><span className="tiny-label">{connected ? 'LIVE' : 'OFFLINE'} <i className={connected ? 'live-dot' : 'muted-dot'}/></span></div>
          <div className="telemetry-card"><div className="telemetry-top"><span><i/> PROCESSOR ACTIVITY</span><Cpu size={14}/></div><div className="cpu-value">{status && connected ? Math.round(status.metrics.cpu_percent) : '—'}<span>%</span><small>CPU utilization</small></div><div className="graph"><div className="graph-lines"/>{samples.length > 1 ? <svg viewBox="0 0 240 72" preserveAspectRatio="none" aria-label="Real CPU utilization samples"><defs><linearGradient id="graph-fill" x1="0" x2="0" y1="0" y2="1"><stop stopColor="#62d0bc" stopOpacity=".22"/><stop offset="1" stopColor="#62d0bc" stopOpacity="0"/></linearGradient></defs><path d={`M0 72 ${samples.map((v,i)=>`L${i/(samples.length-1)*240} ${68-v*.6}`).join(' ')} L240 72 Z`} fill="url(#graph-fill)"/><polyline points={samples.map((v,i)=>`${i/(samples.length-1)*240},${68-v*.6}`).join(' ')} stroke="#67c7b2" strokeWidth="1.4" fill="none"/></svg> : <span className="graph-wait">Collecting live samples</span>}</div><div className="telemetry-foot"><span>2 SECOND SAMPLES</span><span>{connected ? 'ON DEVICE' : 'LAST RECEIVED'}</span></div></div>
          <div className="resource-row"><div className="resource-icon"><Database size={15}/></div><div><span>Memory</span><small>{status ? `${status.metrics.memory_used_gb} / ${status.metrics.memory_total_gb} GB` : 'Waiting for service'}</small></div><strong>{status ? Math.round(status.metrics.memory_percent) : '—'}<small>%</small></strong></div><div className="resource-meter"><div style={{width:`${status?.metrics.memory_percent || 0}%`}}/></div>
          <div className="resource-row"><div className="resource-icon"><HardDrive size={15}/></div><div><span>Storage</span><small>System drive used</small></div><strong>{status ? Math.round(status.metrics.disk_percent) : '—'}<small>%</small></strong></div><div className="resource-meter storage-meter"><div style={{width:`${status?.metrics.disk_percent || 0}%`}}/></div>
        </section>
        <section className="brief-section"><div className="panel-heading"><span><span className="heading-line"/> YOUR WORKSPACE</span><span className="tiny-label">{clock.toLocaleDateString('en', {month:'short',day:'2-digit'}).toUpperCase()}</span></div><button className="brief-item" onClick={showTasks}><div className="brief-icon"><ListTodo size={15}/></div><div><strong>{status?.counts.tasks || 0} tasks in your workspace</strong><small>A little progress, every day.</small></div><ChevronRight size={14}/></button><button className="brief-item" onClick={() => {setTab('notes');}}><div className="brief-icon"><NotebookPen size={15}/></div><div><strong>{status?.counts.notes || 0} saved notes</strong><small>A place for your next idea.</small></div><ChevronRight size={14}/></button><div className="headlines-notice"><Radio size={13}/><p>Search current headlines and sources.<br/><button onClick={() => setPanel('research')}>Open web intelligence <ArrowUpRight size={11}/></button></p></div></section>
        <footer className="rail-footer"><ShieldCheck size={14}/><span>YOUR DEVICE. YOUR WORKSPACE.</span></footer>
      </aside>

      <section className="center-workspace">
        <div className="workspace-topline"><span className="eyebrow">INTELLIGENCE WORKSPACE</span><span className="tiny-label"><i className="subtle-dot"/> {connected ? 'CORE ONLINE' : 'WAITING FOR BACKEND'}</span></div>
        <section className="core-stage" aria-label="STONIC intelligence core">
          <div className="node-field"><div className="node-field-label"><Network size={12}/><span>CONNECTED BY DESIGN</span></div><svg className="connections" viewBox="0 0 500 340" preserveAspectRatio="none" aria-hidden="true"><defs><filter id="line-glow"><feGaussianBlur stdDeviation="3"/></filter></defs>{[['M176 67 C310 67 300 170 380 170 L500 170','#78bc80'],['M176 135 C268 135 315 170 380 170','#a89ec6'],['M176 203 C272 203 303 170 380 170','#73a2ec'],['M176 271 C300 271 318 170 380 170','#d07984']].map(([d,color])=><g key={color}><path d={d} fill="none" stroke={color} strokeWidth="3" opacity=".18" filter="url(#line-glow)"/><path d={d} fill="none" stroke={color} strokeWidth="1.5" opacity=".65"/></g>)}<path d="M380 170 H500" stroke="#82cfdd" strokeWidth="1.4"/><circle cx="380" cy="170" r="4" fill="#b4e4e9"/><circle cx="380" cy="170" r="9" fill="#b4e4e9" opacity=".08"/><circle cx="449" cy="170" r="2" fill="#b4e4e9"/></svg>
          <div className="core-nodes"><button className="core-node memory-node" onClick={() => setPanel('memory')}><span className="node-icon"><Brain size={19}/></span><span>Memory<small>{status?.counts.memory || 0} saved memories</small></span><i/></button><button className="core-node soul-node" onClick={() => settings('Personalization')}><span className="node-icon"><Fingerprint size={19}/></span><span>Soul<small>Your preferences</small></span><i/></button><button className="core-node skills-node" onClick={() => void showSkills()}><span className="node-icon"><BookOpen size={18}/></span><span>Skills<small>Tools & capabilities</small></span><i/></button><button className="core-node settings-node" onClick={() => settings()}><span className="node-icon"><Settings2 size={18}/></span><span>Settings<small>Shape your workspace</small></span><i/></button></div><div className="node-field-bottom"><span>01 — PERSONAL CONTEXT</span><span>02 — CORE</span></div></div>
          <div className="core-card"><div className="core-card-top"><span className="micro-tag">STONIC CORE</span><span className="core-coordinate">V.02</span></div><div className="orb-wrap"><Orb reduced={reduced} active={connected && (status?.activity === 'thinking' || status?.activity === 'executing')}/><div className="orb-orbit orbit-one"/><div className="orb-orbit orbit-two"/><div className="orb-cross cross-left">+</div><div className="orb-cross cross-right">+</div></div><div className="core-identity">S.T.O.N.I.C</div><div className={`core-state ${sending ? 'state-active' : ''}`}><i/>{!connected ? 'SERVICE DISCONNECTED' : sending || status?.activity === 'thinking' ? 'PROCESSING REQUEST' : status?.activity === 'executing' ? 'EXECUTING' : aiReady ? 'INTELLIGENCE CONNECTED' : providerConfigured ? 'PROVIDER NEEDS ATTENTION' : 'LOCAL WORKSPACE READY'}<i/></div><button className="core-action" onClick={() => aiReady ? inputRef.current?.focus() : settings()}><Zap size={13}/>{providerActionLabel}<ArrowRight size={13}/></button><p className="core-footnote" aria-live="polite" title={providerSummary}>{providerSummary}</p></div>
        </section>
        <section className="lower-workspace"><div className="visual-hub panel-surface"><div className="panel-heading"><span><i className="live-dot"/> VISUAL HUB <span className="heading-tag">{visualContent ? 'LOCAL CANVAS' : 'READY'}</span></span><button className="icon-button" aria-label="Expand visual hub" onClick={() => setPanel('visual')}><Expand size={15}/></button></div><div className="visual-body">{visualContent || <div className="empty-state visual-empty"><div className="layer-illustration"><div className="illustration-ring"/><Layers3 size={32} strokeWidth={1.2}/><span className="spark-point p1"/><span className="spark-point p2"/></div><span className="eyebrow">SPACE FOR YOUR IDEAS</span><h2>See the bigger picture.</h2><p>Bring an image into focus, capture your screen,<br className="desktop-break"/> or map out what comes next.</p><div className="visual-buttons"><button className="secondary-button" onClick={() => upload.current?.click()}><ImagePlus size={14}/> Add an image</button><button className="quiet-button" onClick={() => {setFlowDraft('');setPanel('flow');}}><Workflow size={14}/> Create a flow</button></div><div className="visual-capabilities"><span>IMAGES</span><span>SCREEN CAPTURES</span><span>FLOWCHARTS</span></div></div>}</div><div className="visual-footer"><span><ShieldCheck size={11}/> {visualContent ? 'LOCAL ONLY · NOT SENT TO AI' : 'A LOCAL CANVAS. NOTHING UPLOADED.'}</span>{visualContent ? <div><button className="text-button" onClick={() => setPanel('vision')}>Analyze image</button><button className="icon-button" aria-label="Add another image" onClick={() => upload.current?.click()}><Plus size={14}/></button><button className="icon-button" aria-label="Clear visual hub" onClick={() => {setImageUrl('');setFlow([]);}}><Trash2 size={13}/></button></div> : <span className="corner-mark">⌁</span>}</div></div>
          <div className="agents-panel panel-surface"><div className="panel-heading"><span><GitBranch size={13}/> TASK ACTIVITY</span><button className="icon-button" aria-label="Expand task activity" onClick={() => setPanel('activity')}><Expand size={14}/></button></div><TaskActivity onChange={() => {api<Message[]>(`/chat/${session}`).then(setMessages).catch(e => setToast(e.message)); void refresh();}}/><div className="agents-footer"><ShieldCheck size={12}/> APPROVALS · PROGRESS · VERIFIED RESULTS</div></div></section>
        <footer className="workspace-footer"><div className="capability-actions"><button onClick={() => void captureScreen()}><Monitor size={13}/><span>SCREEN</span></button><button onClick={() => setPanel('permissions')}><ShieldCheck size={13}/><span>PC CONTROL</span></button></div><span className="workspace-version">STONIC V2 / 0.2</span></footer>
      </section>

      <aside className="conversation-panel panel-surface"><div className="conversation-header"><nav aria-label="Workspace tabs">{(['chats','logs','notes','tasks'] as Tab[]).map(name => <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)}>{name.toUpperCase()}{name === 'chats' && tab === name ? <span/> : null}</button>)}</nav><button className="icon-button" disabled={sending} aria-label="New conversation" title="New conversation" onClick={newChat}><Plus size={17}/></button></div>
        {tab === 'chats' ? <><div className="chat-body">{messages.length ? <div className="messages">{messages.map(message => <article key={message.id} className={`message message-${message.role}`}><div className="message-label">{message.role === 'assistant' ? <><BrandMark small/> STONIC</> : <><span className="user-avatar">{String(config?.values.display_name || 'Y')[0].toUpperCase()}</span> YOU</>}<time>{new Date(message.created_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</time></div><div className="message-content">{message.content}</div></article>)}{streamingText ? <article className="message message-assistant"><div className="message-label">STONIC · RESPONDING</div><div className="message-content">{streamingText}</div></article> : sending ? <div className="thinking-indicator"><span/><span/><span/> Processing your request</div> : null}<div ref={chatEnd}/></div> : <div className="chat-welcome"><div className="welcome-icon"><Bot size={28} strokeWidth={1.25}/><span/></div><span className="eyebrow">{aiReady ? 'SYSTEM READY' : providerConfigured ? 'PROVIDER NEEDS ATTENTION' : 'YOUR PERSONAL WORKSPACE'}</span><h1>A space to think.<br/>A place to begin.</h1><p>{aiReady ? 'Ask a question, explore an idea, or pick up where you left off.' : providerConfigured ? 'Your provider credentials and model are saved. Open AI & Providers to see the current provider status.' : 'Connect your AI to start a conversation. Your notes, tasks, and memories are ready now.'}</p><div className="suggestions"><button onClick={() => void send('/status')}><Activity size={14}/><span>How is my system doing?</span><ArrowUpRight size={13}/></button><button onClick={() => setTab('notes')}><NotebookPen size={14}/><span>Capture a new thought</span><ArrowUpRight size={13}/></button><button onClick={() => settings()}><SlidersIcon/><span>Set up my intelligence provider</span><ArrowUpRight size={13}/></button></div><span className="welcome-note"><ShieldCheck size={12}/> Built around you. Stored on your device.</span></div>}</div><div className="composer-area"><form className="composer" onSubmit={e => {e.preventDefault();void send();}}><textarea ref={inputRef} aria-label="Message STONIC" rows={2} maxLength={12000} placeholder={connected ? 'Type an instruction…' : 'Waiting for local service…'} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => {if(e.key === 'Enter' && !e.shiftKey){e.preventDefault();void send();}}}/><div className="composer-bottom"><button type="button" className="icon-button" aria-label="Add image to visual hub" onClick={() => upload.current?.click()}><Plus size={16}/></button><VoiceControl session={session} onSettings={settings} onNotice={setToast}/><span>Shift + Enter for a new line</span>{sending ? <button type="button" className="send-button stop-button" aria-label="Stop generation" onClick={() => {api('/chat/cancel',{method:'POST'}).catch(e=>setToast(e.message));}}><Square size={13}/></button> : <button className="send-button" aria-label="Send message" disabled={!input.trim() || !connected}><ArrowUp size={18}/></button>}</div></form><div className="composer-status"><span><BrandMark small/> Main assistant</span><button onClick={() => settings()} title={providerCheck?.detail || undefined}><i className={aiReady ? 'live-dot' : 'warning-dot'}/>{providerStatusLabel}</button></div><div className="composer-footnote"><span>{config?.values.save_conversations ? 'CONVERSATIONS SAVED LOCALLY' : 'CONVERSATION SAVING IS OFF'}</span><CircleHelp size={12}/></div></div></> : tab === 'logs' ? <div className="logs-view"><div className="log-title"><span>Runtime activity</span><span className="micro-tag">{logs.length} EVENTS</span></div>{logs.length ? logs.map(log => <article key={log.id} className={`log-entry log-${log.level}`}><span className="log-dot"/><div><header><span>{log.subsystem}</span><time>{new Date(log.time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}</time></header><p>{log.message}</p></div></article>) : <p className="loading-text">Waiting for diagnostic events…</p>}</div> : <Records key={tab} kind={tab} onChange={() => void refresh()} onDirtyChange={trackDirty}/>}
      </aside>
    </main>
    <input ref={upload} hidden type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={e => {void loadImage(e.target.files?.[0]);e.target.value='';}}/>
    {toast ? <div className="toast" role="status"><span>{toast}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setToast('')}><X size={14}/></button></div> : null}
    {visible('activity') ? <Modal title="Task activity" subtitle="Review actions, approvals and verification." onClose={() => closePanel('activity')} wide><TaskActivity onChange={() => {api<Message[]>(`/chat/${session}`).then(setMessages).catch(e => setToast(e.message)); void refresh();}}/></Modal> : null}
    {visible('productivity') ? <Modal title="Reminders & notifications" subtitle="Your schedule and local notices." onClose={() => closePanel('productivity')} wide><Productivity/></Modal> : null}
    {visible('research') ? <Modal title="Web intelligence" subtitle="Current information with retrieved sources." onClose={() => closePanel('research')} wide><Research/></Modal> : null}
    {visible('gaming') ? <Modal title="Gaming intelligence" subtitle="Your games, measured performance and quiet mode." onClose={() => closePanel('gaming')} wide><Gaming/></Modal> : null}
    {firstRun&&<FirstRun onDone={finishSetup} onConfigure={()=>{finishSetup();settings();}}/>}
    {visible('system')&&<Modal title="System monitor" subtitle="Current resources and recent activity." onClose={()=>closePanel('system')} wide><SystemMonitor status={status} samples={samples} connected={connected}/></Modal>}
    {visible('settings') ? <SettingsPanel initialCategory={category} onClose={() => closePanel('settings')} onSaved={() => void reloadConfig()}/> : null}
    {visible('memory') ? <Modal title="Memory" subtitle="Useful context, kept close." onClose={() => closePanel('memory')}><Records kind="memory" onChange={() => void refresh()} onDirtyChange={trackDirty}/></Modal> : null}
    {visible('skills') ? <Modal title="Skills & capabilities" subtitle="Registered tools and reviewed extensions." onClose={() => closePanel('skills')} wide><Skills tools={skills}/></Modal> : null}
    {visible('diagnostics') ? <Modal title="System diagnostics" subtitle="An honest view of what is ready, and what is next." onClose={() => closePanel('diagnostics')} wide><div className="modal-content"><div className="diagnostic-banner"><Activity size={22}/><div><strong>{connected ? 'Workspace health: ' + status?.health + '' : 'Backend connection lost'}</strong><p>{connected ? 'Each check below reflects current configuration, device or provider evidence.' : 'Restart the launcher to reconnect. Previously displayed metrics may be stale.'}</p></div><button className="icon-button" aria-label="Refresh diagnostics" onClick={() => void refresh()}><RefreshCw size={17}/></button></div>{status?.checks.map(check => <article className="health-row" key={check.id}><span className={check.status === 'ready' ? 'live-dot' : 'warning-dot'}/><div><strong>{check.name}</strong><p>{check.detail}</p></div><span className={`status-label ${check.status === 'ready' ? '' : 'warning'}`}>{connected ? check.status : 'stale'}</span></article>)}</div></Modal> : null}
    {visible('permissions') ? <Modal title="Computer control" subtitle="Observed windows and reviewed actions." onClose={() => closePanel('permissions')} wide><ComputerControl/></Modal> : null}
    {visible('vision') ? <Modal title="Visual intelligence" subtitle="Understand the image you selected." onClose={() => closePanel('vision')} wide><VisionPanel imageUrl={imageUrl}/></Modal> : null}
    {visible('commands') ? <Modal title="Command center" onClose={() => closePanel('commands')}>
      <div className="command-search"><Search size={19}/><input aria-label="Search commands" placeholder="Where would you like to go?" value={commandQuery} onChange={e => setCommandQuery(e.target.value)} onKeyDown={e => {if(e.key === 'Enter' && commands[0]) commands[0].action(); if(e.key === 'ArrowDown') {e.preventDefault();document.querySelector<HTMLButtonElement>('.command-result')?.focus();}}}/><kbd>ESC</kbd></div>
      {!commandQuery&&<nav className="quick-access-grid" aria-label="Quick access">{[
        {label:'CONFIG',icon:Settings2,action:()=>settings()}, {label:'MEMORY',icon:Brain,action:()=>setPanel('memory')},
        {label:'TASKS',icon:ListTodo,action:()=>setPanel('activity')}, {label:'WEB',icon:Search,action:()=>setPanel('research')},
        {label:'VISION',icon:Monitor,action:()=>setPanel('vision')},
        {label:'SYSTEM',icon:Activity,action:()=>setPanel('system')}, {label:'SKILLS',icon:BookOpen,action:()=>void showSkills()},
        {label:'EVENTS',icon:Radio,action:()=>setPanel('productivity')}, {label:'DIAGNOSTICS',icon:ShieldCheck,action:()=>setPanel('diagnostics')},
      ].map(({label,icon:Icon,action})=><button key={label} onClick={action}><Icon size={19}/><span>{label}</span></button>)}</nav>}
      <div className="command-results">{commands.length ? commands.map((command,i) => <button className="command-result" key={command.name} onClick={command.action} onKeyDown={e => {if(e.key === 'ArrowDown' || e.key === 'ArrowUp'){e.preventDefault();const items=document.querySelectorAll<HTMLButtonElement>('.command-result');items[(i+(e.key === 'ArrowDown'?1:-1)+items.length)%items.length]?.focus();}}}><Command size={16}/><div><strong>{command.name}</strong><small>{command.hint}</small></div><ArrowUpRight size={15}/></button>) : <p className="loading-text">No matching commands.</p>}</div>
    </Modal> : null}
    {visible('visual') ? <Modal title="Visual hub" subtitle={imageUrl ? imageName : 'Your local canvas'} wide onClose={() => closePanel('visual')}><div className="expanded-visual">{visualContent || <div className="empty-state"><Layers3 size={32}/><h3>A fresh canvas</h3><p>Add an image or create a flow to fill this space.</p><button className="secondary-button" onClick={() => upload.current?.click()}><ImagePlus size={15}/> Add an image</button></div>}</div></Modal> : null}
    {visible('flow') ? <Modal title="Create a flow" subtitle="Map your own steps into a simple visual sequence." onClose={() => closePanel('flow')}><form className="modal-content flow-form" onSubmit={e => {e.preventDefault();setFlow(flowDraft.split('\n').map(s=>s.trim()).filter(Boolean).slice(0,10));setImageUrl('');closePanel('flow');}}><label>One step per line<textarea aria-label="Flow steps" rows={7} maxLength={1600} placeholder={'Define the idea\nExplore possibilities\nMake a plan\nBring it to life'} value={flowDraft} onChange={e => setFlowDraft(e.target.value)}/></label><p className="muted">Up to 10 steps. This creates a local diagram from your text; AI generation is not connected.</p><button className="primary-button" disabled={!flowDraft.trim()}><Workflow size={15}/> Create flow</button></form></Modal> : null}
  </div></PanelLayoutContext.Provider>;
}

function SlidersIcon() { return <Settings2 size={14}/>; }
export default App;
