import type { GenerationProgress } from './types';
export interface AnonymousAccount { id: string; name: string; createdAt: string; lastSeenAt: string; status: 'active' | 'blocked'; risk: 'normal' | 'watch' | 'high'; requestsLastMinute: number; generationsToday: number; rateLimitHits: number; activeGenerations: number; ipLabel: string; blockReason: string; }
export interface AbuseEvent { id: string; accountId: string; time: string; kind: 'rate_limited' | 'account_blocked' | 'account_unblocked' | 'generation_rejected'; detail: string; }
export interface AnonymousPolicy { requestsPerMinute: number; generationsPerDay: number; maxConcurrentGenerations: number; accountsPerIpHour: number; }
export interface AnonymousSession { kind: 'anonymous'; userId: string; name: string; onboardingCompleted: boolean; }
export class DemoHttpError extends Error { constructor(message: string, public status: number, public retryAfter: number) { super(message); } }
async function request<T>(path: string, body?: unknown, method = body === undefined ? 'GET' : 'POST'): Promise<T> {
  const response = await fetch(`/__demo${path}`, { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-Prototype-Request': '1' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok) throw new DemoHttpError(data.message || '请求失败，请稍后重试。', response.status, Number(response.headers.get('Retry-After')) || 0);
  return data as T;
}
export const anonymousApi = {
  session: () => request<{ session: AnonymousSession; generation: GenerationProgress | null }>('/anonymous/session', {}),
  touch: () => request<void>('/anonymous/touch', {}),
  onboard: () => request<void>('/anonymous/onboarding', {}),
  generate: (partial = false) => request<GenerationProgress>('/anonymous/generation', { partial }),
  progress: () => request<GenerationProgress | null>('/anonymous/generation'),
  cancel: () => request<GenerationProgress>('/anonymous/generation/cancel', {}),
};
export const anonymousAdminApi = {
  login: (email: string, password: string) => request<void>('/admin/session', { email, password }),
  session: () => request<{ kind: 'admin'; userId: string; name: string }>('/admin/session'),
  logout: () => request<void>('/admin/session', undefined, 'DELETE'),
  list: () => request<{ users: AnonymousAccount[]; events: AbuseEvent[]; policy: AnonymousPolicy }>('/admin/anonymous'),
  setStatus: (id: string, status: 'active' | 'blocked', reason: string) => request<void>(`/admin/anonymous/${encodeURIComponent(id)}/status`, { status, reason }),
  savePolicy: (policy: AnonymousPolicy) => request<void>('/admin/policy', policy, 'PUT'),
  simulateAbuse: (id: string) => request<void>(`/admin/anonymous/${encodeURIComponent(id)}/simulate`, {}),
};
