import { reactive } from 'vue';
import { api, ApiError, type Session } from '@zhigenews/api-client';

export const sessionState = reactive<{ session: Session | null; checked: boolean; error: ApiError | Error | null }>({ session: null, checked: false, error: null });
let pending: Promise<Session | null> | undefined;
export function restoreSession(force = false): Promise<Session | null> {
  if (pending) return pending;
  if (sessionState.checked && !force) return Promise.resolve(sessionState.session);
  pending = api<Session>('getSession').then(session => {
    sessionState.session = session; sessionState.error = null; return session;
  }).catch(error => {
    sessionState.session = null;
    sessionState.error = error instanceof ApiError && error.status === 401 ? null : error;
    return null;
  }).finally(() => { sessionState.checked = true; pending = undefined; });
  return pending;
}
export async function enterSession() {
  const session = await api<Session>('ensureAnonymousSession');
  sessionState.session = session; sessionState.checked = true; sessionState.error = null;
  return session;
}
export function captureAccessError(error: unknown): boolean {
  if (!(error instanceof ApiError) || ![401, 403].includes(error.status)) return false;
  sessionState.session = null;
  sessionState.error = error.status === 403 ? error : null;
  sessionState.checked = true;
  return true;
}
export const TOPICS = ['Agent 工程', '大语言模型', '开源生态', 'AI 产品', '多模态', '算力与芯片', 'AI 安全', '研究论文'];
export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间未知' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
}
export function errorMessage(error: unknown): string {
  captureAccessError(error);
  return error instanceof Error ? error.message : '请求失败，请重试。';
}
export function safeExternalUrl(value: string): string | undefined {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined; } catch { return undefined; }
}
