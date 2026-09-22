import type { Status } from '../api';
export function SystemMonitor({status,samples,connected}:{status:Status|null;samples:number[];connected:boolean}) {
  if(!status)return <div className="modal-content"><p>Waiting for a system sample…</p></div>;
  const points=samples.map((value,index)=>`${index*600/Math.max(1,samples.length-1)},${140-value*1.4}`).join(' ');
  return <div className="modal-content"><p className="muted">{connected?'Live measurements from this device.':'Connection lost. These are the last received measurements.'}</p><div className="system-metrics-grid">{[
    ['CPU',`${status.metrics.cpu_percent}%`],['Memory',`${status.metrics.memory_used_gb} / ${status.metrics.memory_total_gb} GB`],['System drive',`${status.metrics.disk_percent}% used`],
  ].map(([name,value])=><article className="job-card" key={name}><span className="micro-tag">{name}</span><h3>{value}</h3></article>)}</div><h3>Recent CPU activity</h3><svg className="cpu-history" viewBox="0 0 600 150" role="img" aria-label="CPU usage sampled every two seconds"><path d="M0 140H600 M0 70H600 M0 0H600" stroke="#26373d" fill="none"/><polyline points={points} fill="none" stroke="#65d8de" strokeWidth="2"/></svg><p>{status.metrics.cpu_count} logical processors · {status.metrics.platform}</p><p className="muted">Stonic service uptime: {Math.floor(status.metrics.uptime_seconds/60)} minutes. {status.metrics.battery_percent===null?'No battery percentage reported.':`Reported battery: ${status.metrics.battery_percent}%.`}</p></div>;
}
