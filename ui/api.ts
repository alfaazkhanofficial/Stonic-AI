export interface HealthCheck { id: string; name: string; status: 'ready'|'unavailable'|'unconfigured'|'degraded'|'initializing'|'recovering'|'failed'; detail: string }
export interface Metrics { cpu_percent: number; memory_percent: number; memory_used_gb: number; memory_total_gb: number; disk_percent: number; uptime_seconds: number; platform: string; cpu_count: number; battery_percent: number|null }
export interface Status { version: string; health: string; activity: string; metrics: Metrics; checks: HealthCheck[]; counts: {notes: number; tasks: number; memory: number} }
export interface LogEvent { id: string; time: string; subsystem: string; level: string; message: string }
export interface WorkspaceRecord { memory_type?: string; id: string; kind: string; title: string; content: string; status: 'open'|'done'; created_at: string; updated_at: string }
export interface Message { id: string; session_id: string; role: string; content: string; created_at: string }
export type SettingValue = string | number | boolean;
export interface ConfigField { title?: string; type: string; default?: SettingValue; enum?: string[]; category?: string; help?: string; internal?: boolean; minimum?: number; maximum?: number; maxLength?: number; restart_required?: boolean }
export interface ConfigResponse { schema: { properties: Record<string, ConfigField> }; values: Record<string, SettingValue>; credential_configured: boolean; credential_required: boolean }
export interface VoiceStatus { state: string; detail: string; running: boolean; muted: boolean; session_id: string; push_to_talk: string; push_to_talk_held: boolean; push_to_talk_global: boolean; barge_in: string; barge_in_active: boolean; consent: boolean; credential_configured: boolean; model: string; input_device: string|null; output_device: string|null; echo: {calibrated: boolean; reliable: boolean; floor: number; threshold: number; required_blocks: number}|null }
export interface VoiceDevices { available: boolean; input: string[]; output: string[]; reason?: string }
export interface Skill { name: string; description: string; permission_level: number }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: 'The service could not be reached.' }));
    const detail = Array.isArray(data.detail) ? data.detail.map((e: {loc: string[]; msg: string}) => `${e.loc.join('.')}: ${e.msg}`).join('\n') : data.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

declare global {
  interface Window {
    stonicDesktop?: {
      windowAction: (action: 'minimize'|'maximize'|'close') => void;
      captureScreen: () => Promise<string | null>;
      notify: (notice:{title:string;body:string;quiet?:boolean}) => void;
      onBackendStatus: (callback:(data:{state:string;message:string})=>void) => ()=>void;
    }
  }
}
