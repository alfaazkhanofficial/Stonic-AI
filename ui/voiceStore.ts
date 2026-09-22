/** Live voice levels, shared without React re-renders (they arrive ~12 times a second). */
export interface VoiceSnapshot { state: string; levelIn: number; levelOut: number }

let snapshot: VoiceSnapshot = { state: 'off', levelIn: 0, levelOut: 0 };
const listeners = new Set<() => void>();

export const voiceStore = {
  get: () => snapshot,
  set(patch: Partial<VoiceSnapshot>) {
    snapshot = { ...snapshot, ...patch };
    listeners.forEach(listener => listener());
  },
  subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
};
