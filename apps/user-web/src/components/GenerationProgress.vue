<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { CircleCheck, Clock3, RotateCcw, Square } from 'lucide-vue-next';
import type { GenerationProgress as GenerationState } from '@zhigenews/api-client';
const props = defineProps<{ progress: GenerationState; busy?: boolean }>();
defineEmits<{ cancel: []; retry: [] }>();
const now = ref(Date.now());
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { timer = setInterval(() => { now.value = Date.now(); }, 1000); });
onBeforeUnmount(() => clearInterval(timer));
const active = computed(() => ['queued', 'running', 'cancelling'].includes(props.progress.status));
const percent = computed(() => props.progress.percent === null ? undefined : Math.max(0, Math.min(active.value ? 99 : 100, Math.round(props.progress.percent))));
const title = computed(() => ({ queued: '等待生成', running: '正在生成简报', cancelling: '正在取消…', cancelled: '已取消生成', failed: '生成失败', completed: '简报已更新', partial: '简报已更新' })[props.progress.status]);
const remaining = computed(() => {
  if (props.progress.status === 'cancelling') return '正在取消…';
  if (props.progress.remainingSeconds === null) return '时间估算中';
  const elapsed = Math.max(0, now.value - Date.parse(props.progress.updatedAt)) / 1000;
  const seconds = Math.ceil(props.progress.remainingSeconds - elapsed);
  if (seconds <= 0) return '正在完成，时间估算中';
  if (seconds >= 60) return `预计剩余约 ${Math.ceil(seconds / 60)} 分钟`;
  return `预计剩余约 ${seconds} 秒`;
});
</script>
<template>
  <section class="generation-progress" :class="{ 'is-failed': progress.status === 'failed' }" aria-label="简报生成进度">
    <div class="generation-heading"><span class="generation-title" role="status"><CircleCheck v-if="['completed', 'partial'].includes(progress.status)" :size="16" aria-hidden="true" />{{ title }}</span><span v-if="active && percent !== undefined" class="generation-percent" aria-hidden="true">{{ percent }}%</span></div>
    <progress v-if="active" class="generation-bar" max="100" :value="percent" aria-label="简报生成进度" :aria-valuetext="percent === undefined ? '进度估算中' : `${percent}%`"></progress>
    <p v-if="active && progress.error" class="generation-notice" role="status">{{ progress.error }}</p>
    <div class="generation-footer"><span v-if="active" class="generation-time"><Clock3 :size="14" aria-hidden="true" />{{ remaining }}</span><p v-else-if="progress.status === 'failed'" role="alert">{{ progress.error || '暂时无法生成，请重试。' }}</p><p v-else-if="progress.status === 'cancelled'">现有简报已保留。</p><p v-else-if="progress.status === 'partial'">部分来源暂不可用，已保留完成的内容。</p><button v-if="active" class="button button--ghost generation-action" :disabled="busy || progress.status === 'cancelling'" @click="$emit('cancel')"><Square :size="12" aria-hidden="true" />{{ busy || progress.status === 'cancelling' ? '正在取消…' : '取消' }}</button><button v-else-if="['failed', 'cancelled'].includes(progress.status)" class="button button--ghost generation-action" :disabled="busy" @click="$emit('retry')"><RotateCcw :size="14" aria-hidden="true" />重新生成</button></div>
  </section>
</template>
<style scoped>
.generation-progress { padding: 16px 20px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-card); background: var(--color-primary-soft); margin-bottom: 24px; }
.generation-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; font-size: 14px; color: var(--color-primary); }
.generation-title { display: inline-flex; align-items: center; gap: 6px; font-weight: 500; }
.generation-percent { font-variant-numeric: tabular-nums; }
.generation-bar { appearance: none; display: block; width: 100%; height: 6px; margin-top: 12px; border: 0; border-radius: var(--radius-pill); overflow: hidden; background: var(--color-primary-border); accent-color: var(--color-primary); }
.generation-bar::-webkit-progress-bar { background: var(--color-primary-border); border-radius: var(--radius-pill); }
.generation-bar::-webkit-progress-value { background: var(--color-primary); border-radius: var(--radius-pill); transition: width var(--duration-normal) var(--ease-standard); }
.generation-bar::-moz-progress-bar { background: var(--color-primary); border-radius: var(--radius-pill); }
.generation-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 4px 12px; margin-top: 4px; font-size: 13px; color: var(--color-text-secondary); }
.generation-time { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; }
.generation-action { min-height: 44px; padding-inline: 8px; font-size: 13px; }
.generation-notice { margin: 12px 0 0; color: var(--color-text-secondary); font-size: 13px; line-height: 22px; }
.generation-footer p { margin: 8px 0 0; }
.is-failed { border-color: var(--color-danger-border); background: var(--color-danger-bg); }
.is-failed .generation-title { color: var(--color-danger); }
@media (max-width: 480px) { .generation-progress { padding: 12px 16px; } }
@media (prefers-reduced-motion: reduce) { .generation-bar::-webkit-progress-value { transition: none; } }
</style>
