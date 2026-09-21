import { onBeforeUnmount, ref, type Ref } from 'vue';
import { api, ApiError, type Brief, type GenerationProgress } from '@zhigenews/api-client';

/** Follow one durable generation across connection loss; never submit a new run here. */
export function useGeneration(brief: Ref<Brief | null>, onError: (error: unknown) => void) {
  const progress = ref<GenerationProgress | null>(null), reconnecting = ref(false);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let request: AbortController | undefined;
  let revision = 0, stopped = false, runId: string | undefined;
  const active = (value: GenerationProgress | null) => !!value && ['queued', 'running', 'cancelling'].includes(value.status);
  function schedule(delay = 2000) {
    clearTimeout(timer);
    if (!stopped) timer = setTimeout(poll, delay);
  }
  async function apply(value: GenerationProgress | null, current: number, signal: AbortSignal) {
    if (current !== revision || stopped) return;
    runId = value?.id;
    // Only announce the update once its readable content has arrived.
    if (value?.briefId && ['completed', 'partial'].includes(value.status) && brief.value?.id !== value.briefId) {
      const next = await api<Brief>('getBrief', { path: { id: value.briefId }, signal });
      if (current !== revision || stopped) return;
      brief.value = next;
    }
    progress.value = value;
    reconnecting.value = false;
    if (active(value)) schedule();
  }
  function failed(error: unknown, current: number) {
    if (current !== revision || stopped) return;
    if (error instanceof ApiError && error.status >= 400 && error.status < 500 && ![408, 429].includes(error.status)) {
      reconnecting.value = false;
      onError(error);
      return;
    }
    reconnecting.value = true;
    schedule(error instanceof ApiError && error.status === 429 ? Math.max(1, error.retryAfter ?? 60) * 1000 : 3000);
  }
  async function accept(value: GenerationProgress | null) {
    clearTimeout(timer); request?.abort();
    const current = ++revision;
    request = new AbortController();
    try { await apply(value, current, request.signal); }
    catch (error) { failed(error, current); }
  }
  async function poll() {
    clearTimeout(timer); request?.abort();
    if (stopped) return;
    const current = ++revision;
    request = new AbortController();
    try {
      const value = runId
        ? await api<GenerationProgress>('getGenerationProgress', { path: { id: runId }, signal: request.signal })
        : await api<GenerationProgress | null>('getCurrentGeneration', { signal: request.signal });
      await apply(value, current, request.signal);
    } catch (error) { failed(error, current); }
  }
  onBeforeUnmount(() => { stopped = true; ++revision; clearTimeout(timer); request?.abort(); });
  return { progress, reconnecting, accept, poll };
}
