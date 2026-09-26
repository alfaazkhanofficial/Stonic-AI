import { useCallback, useEffect, useState } from 'react';
import { Check, ShieldCheck, Square, RefreshCw, OctagonAlert } from 'lucide-react';
import { api } from '../api';

interface Step {id: string; title: string; tool: string; status: string; attempts: number; result: {message: string; verification?: string; data: Record<string, unknown>} | null}
interface Job {id: string; goal: string; status: string; error?: string; steps: Step[]; approval: {id: string; level: number; description: string; arguments: Record<string, unknown>} | null}
interface Confirm {tool: string; arguments: Record<string, unknown>; risk: string}
interface AgentGoal {id: string; goal: string; status: string; autonomy: string; updated_at: string}
interface AgentGoalDetail extends AgentGoal {actions: {tool: string; status: string; message: string; verification: string; time: string}[]; confirm?: Confirm[]}

function AgentGoalCard({ goal, onChange }: {goal: AgentGoal; onChange: () => void}) {
  const [detail, setDetail] = useState<AgentGoalDetail | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const waiting = goal.status === 'waiting_approval';
  useEffect(() => { if (waiting) api<AgentGoalDetail>(`/agent/goals/${goal.id}`).then(setDetail).catch(() => {}); }, [goal.id, waiting]);
  async function decide(approved: boolean) {
    setBusy(true); setError('');
    try { await api(`/agent/goals/${goal.id}/decision`, {method: 'POST', body: JSON.stringify({approved})}); onChange(); }
    catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <article className="job-card">
    <div className="job-heading"><h3>{goal.goal}</h3><span className={`status-label ${goal.status === 'completed' ? '' : 'warning'}`}>{goal.status.replaceAll('_', ' ')}</span></div>
    {error && <p role="alert">{error}</p>}
    {waiting && detail?.confirm?.map((item, i) => <div key={i} className="approval-card">
      <h4><ShieldCheck size={16}/> {item.risk === 'system-critical' ? 'System-critical - review carefully' : 'Review this action'}</h4>
      <p>{item.tool}</p><pre>{JSON.stringify(item.arguments, null, 2)}</pre>
    </div>)}
    {waiting && <div className="action-row">
      <button className="primary-button" disabled={busy} onClick={() => void decide(true)}><Check size={14}/>Approve</button>
      <button className="secondary-button" disabled={busy} onClick={() => void decide(false)}>Decline</button>
    </div>}
  </article>;
}

export function TaskActivity({ onChange }: {onChange?: () => void}) {
  const [jobs, setJobs] = useState<Job[]>([]), [goals, setGoals] = useState<AgentGoal[]>([]), [error, setError] = useState(''), [busy, setBusy] = useState('');
  const refresh = useCallback(async () => {
    try {
      const [jobList, goalList] = await Promise.all([api<Job[]>('/jobs'), api<AgentGoal[]>('/agent/goals').catch(() => [])]);
      setJobs(jobList); setGoals(goalList.filter(g => ['running', 'waiting_approval'].includes(g.status)));
    } catch(e) {setError((e as Error).message);}
  }, []);
  useEffect(() => {void refresh(); const id = setInterval(() => void refresh(), 2000); return () => clearInterval(id);}, [refresh]);
  async function act(job: Job, action: 'approve'|'deny'|'cancel'|'resume') {
    setBusy(job.id); setError('');
    try {
      const decision = action === 'approve' || action === 'deny';
      await api(`/jobs/${job.id}/${decision ? 'decision' : action}`, {method: 'POST', body: decision ? JSON.stringify({approval_id: job.approval?.id, approved: action === 'approve'}) : undefined});
      await refresh(); onChange?.();
    } catch(e) {setError((e as Error).message);}
    finally {setBusy('');}
  }
  async function stopAgent() {
    setBusy('stop-all'); setError('');
    try { await api('/agent/stop', {method: 'POST'}); await refresh(); onChange?.(); }
    catch(e) {setError((e as Error).message);}
    finally {setBusy('');}
  }
  const hasActiveAgentWork = goals.length > 0;
  return <div className="task-activity">
    {error && <p role="alert" className="error-box">{error}</p>}
    {hasActiveAgentWork && <div className="action-row" style={{marginBottom: 12}}>
      <button className="secondary-button" disabled={busy === 'stop-all'} onClick={() => void stopAgent()}><OctagonAlert size={14}/>Stop all agent actions</button>
    </div>}
    {!jobs.length && !goals.length && <div className="activity-empty"><ShieldCheck size={26}/><h3>Ready for a task.</h3><p>Ask Stonic to inspect your workspace, find a note, or carry out a plan. Actions and approvals appear here.</p></div>}
    {goals.map(goal => <AgentGoalCard key={goal.id} goal={goal} onChange={() => { void refresh(); onChange?.(); }}/>)}
    {jobs.map(job => <article key={job.id} className="job-card"><div className="job-heading"><h3>{job.goal}</h3><span className={`status-label ${job.status === 'completed' ? '' : 'warning'}`}>{job.status.replaceAll('_', ' ')}</span></div>
      <ol className="job-steps">{job.steps.map(step => <li key={step.id}><div><strong>{step.title}</strong><span>{step.status.replaceAll('_', ' ')}</span></div>{step.result && <details><summary>{step.result.message}</summary><p>{step.result.verification}</p><pre>{JSON.stringify(step.result.data, null, 2)}</pre></details>}</li>)}</ol>
      {job.error && <p role="alert">{job.error}</p>}
      {job.approval && <div className="approval-card"><h4><ShieldCheck size={16}/> {job.approval.level === 3 ? 'Explicit approval required' : 'Review this action'}</h4><p>{job.approval.description}</p>{typeof job.approval.arguments.capture_id === 'string' && <img style={{maxWidth:'100%',maxHeight:280,objectFit:'contain'}} src={`/api/vision/captures/${job.approval.arguments.capture_id}`} alt="Screen capture awaiting review"/>}<pre>{JSON.stringify(job.approval.arguments, null, 2)}</pre><div className="action-row"><button className="primary-button" disabled={busy === job.id} onClick={() => void act(job, 'approve')}><Check size={14}/>Approve this action</button><button className="secondary-button" disabled={busy === job.id} onClick={() => void act(job, 'deny')}>Deny</button></div></div>}
      {['queued','running','waiting_approval','paused'].includes(job.status) && <div className="action-row">{['paused','waiting_approval'].includes(job.status) && <button className="text-button" disabled={busy === job.id} onClick={() => void act(job, 'resume')}><RefreshCw size={12}/>{job.status === 'waiting_approval' ? 'Refresh approval' : 'Resume plan'}</button>}<button className="text-button" disabled={busy === job.id && job.status !== 'running'} onClick={() => void act(job, 'cancel')}><Square size={12}/>Cancel task</button></div>}
    </article>)}
  </div>;
}
