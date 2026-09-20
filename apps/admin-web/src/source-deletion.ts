import { computed, onBeforeUnmount, ref, shallowRef } from 'vue';
import type { CurrentSourceDeletion, SourceDeletionJob } from '@zhigenews/api-client';
import { errorText, request } from './lib';

export function useSourceDeletion() {
  const job = shallowRef<SourceDeletionJob | null>(null);
  const checked = ref(false), error = ref('');
  const active = computed(() => !!job.value && ['queued', 'running'].includes(job.value.status));
  const unavailable = computed(() => !checked.value || !!error.value || active.value);
  const pendingIds = computed(() => new Set(active.value ? job.value!.items.filter(item => ['pending', 'running'].includes(item.status)).map(item => item.id) : []));
  let controller: AbortController | undefined;
  let revision = 0, polling = false;
  let nextPollAt = 0;
  async function poll(force = true) {
    if (polling || (!force && Date.now() < nextPollAt)) return;
    polling = true;
    const current = ++revision;
    const pending = controller = new AbortController();
    try {
      const result = await request<CurrentSourceDeletion>('currentSourceDeletion', { signal: pending.signal });
      if (current === revision) { job.value = result.job; checked.value = true; error.value = ''; }
    } catch (err) {
      if (current === revision && !pending.signal.aborted) error.value = errorText(err);
    } finally {
      if (current === revision) {
        polling = false;
        nextPollAt = Date.now() + (active.value || error.value ? 1000 : 5000);
      }
    }
  }
  function accept(value: SourceDeletionJob) {
    revision++; controller?.abort(); polling = false; nextPollAt = 0;
    job.value = value; checked.value = true; error.value = '';
  }
  onBeforeUnmount(() => { revision++; controller?.abort(); });
  return { job, checked, error, active, unavailable, pendingIds, poll, accept };
}
