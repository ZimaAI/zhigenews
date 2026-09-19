import { computed, onBeforeUnmount, ref, shallowRef, type Ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import { api, ApiError } from '@zhigenews/api-client';

export async function request<T>(...args: Parameters<typeof api<T>>): Promise<T> {
  try { return await api<T>(...args); }
  catch (error) {
    if (error instanceof ApiError && error.status === 401 && args[0] !== 'adminLogin') window.dispatchEvent(new Event('admin-session-expired'));
    throw error;
  }
}
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const wait = error.retryAfter == null ? '' : ` 请在 ${error.retryAfter} 秒后重试。`;
    const fields = error.fields ? Object.values(error.fields).join('；') : '';
    return `${error.message}${fields ? `：${fields}` : ''}${wait}${error.requestId ? `（请求 ${error.requestId}）` : ''}`;
  }
  return error instanceof Error ? error.message : '请求失败，请重试。';
}
export const toast = ref('');
let toastTimer: ReturnType<typeof setTimeout> | undefined;
export function notify(message: string) { toast.value = message; clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.value = ''; }, 6000); }
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date) : '—';
}
export const number = (value: number | null | undefined, digits = 0) => value == null ? '—' : value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
export function useDirty(dirty: Ref<boolean>) {
  const confirmDiscard = () => !dirty.value || window.confirm('有未保存的修改，确定放弃并离开吗？');
  onBeforeRouteLeave(() => confirmDiscard());
  const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty.value) { event.preventDefault(); event.returnValue = ''; } };
  window.addEventListener('beforeunload', beforeUnload);
  onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload));
  return confirmDiscard;
}
export interface Page<T> { items: T[]; nextCursor: string | null }
export function useCollection<T extends { id: string }>(operationId: string, query: () => Record<string, string | undefined> = () => ({})) {
  const items = shallowRef<T[]>([]); const nextCursor = ref<string | null>(null);
  const loading = ref(false); const loaded = ref(false); const error = ref(''); const refreshedAt = ref('');
  let controller: AbortController | undefined; let revision = 0;
  async function load(more = false) {
    if (more && (loading.value || !nextCursor.value)) return;
    const current = ++revision; controller?.abort(); controller = new AbortController();
    loading.value = true; error.value = '';
    try {
      const page = await request<Page<T>>(operationId, { query: { ...query(), limit: 50, cursor: more ? nextCursor.value : undefined }, signal: controller.signal });
      if (current !== revision) return;
      items.value = more ? [...items.value, ...page.items.filter(item => !items.value.some(previous => previous.id === item.id))] : page.items;
      nextCursor.value = page.nextCursor; loaded.value = true; refreshedAt.value = new Date().toISOString();
    } catch (err) { if (current === revision && !controller.signal.aborted) error.value = errorText(err); }
    finally { if (current === revision) loading.value = false; }
  }
  function replace(item: T) { const index = items.value.findIndex(previous => previous.id === item.id); items.value = index < 0 ? [item, ...items.value] : items.value.map(previous => previous.id === item.id ? item : previous); }
  onBeforeUnmount(() => { revision++; controller?.abort(); });
  return { items, nextCursor, loading, loaded, error, refreshedAt, load, replace, scope: computed(() => `已加载 ${items.value.length} 条${nextCursor.value ? '，仍有更多记录' : ''}`) };
}
export async function allPages<T>(operationId: string): Promise<T[]> {
  const items: T[] = []; let cursor: string | null = null;
  do { const page: Page<T> = await request<Page<T>>(operationId, { query: { limit: 100, cursor } }); items.push(...page.items); cursor = page.nextCursor; } while (cursor);
  return items;
}
export function useRefresh(action: () => void | Promise<void>, milliseconds = 15000) {
  const timer = setInterval(() => { if (document.visibilityState === 'visible') void action(); }, milliseconds);
  onBeforeUnmount(() => clearInterval(timer));
}
/** Reuse a key after an uncertain transport failure; successful acceptance starts a new intent. */
export function intentKeys() { const keys = new Map<string, string>(); return { get: (intent: string) => { if (!keys.has(intent)) keys.set(intent, crypto.randomUUID()); return keys.get(intent)!; }, done: (intent: string) => keys.delete(intent) }; }
