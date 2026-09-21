<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { CircleCheck, CircleAlert, LoaderCircle, RotateCcw, Square } from 'lucide-vue-next';
import type { GenerationProgress as GenerationState } from '@zhigenews/api-client';
const props = defineProps<{ progress: GenerationState | null; busy?: boolean; reconnecting?: boolean }>();
defineEmits<{ cancel: []; retry: [] }>();
const now = ref(Date.now());
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { timer = setInterval(() => { now.value = Date.now(); }, 1000); });
onBeforeUnmount(() => clearInterval(timer));
const active = computed(() => !!props.progress && ['queued', 'running', 'cancelling'].includes(props.progress.status));
const title = computed(() => {
  if (props.reconnecting) return '正在重新连接';
  const value = props.progress;
  if (!value) return '正在准备简报';
  if (value.status === 'failed') return '生成失败，请重试';
  if (value.status === 'cancelled') return '已取消生成';
  if (value.status === 'cancelling') return '正在取消…';
  if (['completed', 'partial'].includes(value.status)) return value.emptyResult ? '本次未发现符合偏好的新内容' : '简报已更新';
  return ({ preparing: '正在准备简报', researching: '正在查找和整理新闻', publishing: '正在保存简报' })[value.phase || 'preparing'];
});
const takingLonger = computed(() => active.value && !props.reconnecting && props.progress?.status !== 'cancelling'
  && now.value - Date.parse(props.progress?.phaseStartedAt || props.progress?.updatedAt || '') >= 30000);
</script>
<template>
  <section class="generation-progress" :class="{ 'is-failed': !reconnecting && progress?.status === 'failed' }" aria-label="简报生成进度">
    <div class="generation-heading" role="status" aria-live="polite" aria-atomic="true">
      <LoaderCircle v-if="active || reconnecting" class="generation-spinner" :size="18" aria-hidden="true" />
      <CircleAlert v-else-if="progress?.status === 'failed'" :size="18" aria-hidden="true" />
      <CircleCheck v-else-if="progress && ['completed', 'partial'].includes(progress.status)" :size="18" aria-hidden="true" />
      <span>{{ title }}</span>
    </div>
    <div v-if="active || reconnecting" class="generation-activity" aria-hidden="true"><span /></div>
    <div v-if="active || takingLonger || progress && ['failed', 'cancelled'].includes(progress.status)" class="generation-footer">
      <p v-if="takingLonger" role="status">仍在整理，请稍候</p>
      <button v-if="active" class="button button--ghost generation-action" :disabled="busy || reconnecting || progress?.status === 'cancelling'" @click="$emit('cancel')"><Square :size="12" aria-hidden="true" />取消</button>
      <button v-else-if="!reconnecting" class="button button--ghost generation-action" :disabled="busy" @click="$emit('retry')"><RotateCcw :size="14" aria-hidden="true" />重新生成</button>
    </div>
  </section>
</template>
<style scoped>
.generation-progress { padding: 16px 20px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-card); background: var(--color-primary-soft); margin-bottom: 24px; }
.generation-heading { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--color-primary); font-weight: 500; }
.generation-heading svg { flex-shrink: 0; }
.generation-spinner { animation: generation-spin 1.4s linear infinite; }
.generation-activity { height: 4px; margin-top: 14px; border-radius: var(--radius-pill); overflow: hidden; background: var(--color-primary-border); }
.generation-activity span { display: block; width: 35%; height: 100%; background: var(--color-primary); border-radius: inherit; animation: generation-travel 2.2s ease-in-out infinite; }
.generation-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 4px 12px; margin-top: 4px; font-size: 13px; color: var(--color-text-secondary); }
.generation-footer p { margin: 8px 0; }
.generation-action { min-height: 44px; padding-inline: 8px; font-size: 13px; margin-left: auto; }
.is-failed { border-color: var(--color-danger-border); background: var(--color-danger-bg); }
.is-failed .generation-heading { color: var(--color-danger); }
@keyframes generation-spin { to { transform: rotate(360deg); } }
@keyframes generation-travel { from { transform: translateX(-100%); } to { transform: translateX(290%); } }
@media (max-width: 480px) { .generation-progress { padding: 12px 16px; } }
@media (prefers-reduced-motion: reduce) { .generation-spinner, .generation-activity span { animation: none; } }
</style>
