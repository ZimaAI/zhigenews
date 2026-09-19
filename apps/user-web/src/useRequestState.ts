import { computed, onBeforeUnmount, ref } from 'vue';
import { ApiError } from '@zhigenews/api-client';
import { errorMessage } from './state';

/** Retry-After is a server deadline, independent of render and polling frequency. */
export function useRequestState() {
  const error = ref(''), retryAt = ref(0), now = ref(Date.now());
  const remaining = computed(() => Math.max(0, Math.ceil((retryAt.value - now.value) / 1000)));
  const timer = setInterval(() => { now.value = Date.now(); }, 1000);
  onBeforeUnmount(() => clearInterval(timer));
  function fail(exception: unknown) {
    error.value = errorMessage(exception);
    if (exception instanceof ApiError && exception.status === 429) retryAt.value = Date.now() + Math.max(1, exception.retryAfter ?? 60) * 1000;
  }
  return { error, remaining, fail, clear: () => { error.value = ''; } };
}
