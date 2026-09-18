<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { ArrowLeft, Square, ArrowUpRight } from 'lucide-vue-next';
import { api, state, formatDate } from '@shared/mock';
import Badge from '@shared/Badge.vue';
import EmptyState from '@shared/EmptyState.vue';
const route = useRoute();
const run = computed(() => state.runs.find((r) => r.id === route.params.id && r.userName === (state.users[0]?.name || '林序')));
const brief = computed(() => state.briefs.find((b) => b.runId === route.params.id));
const busy = ref(false), error = ref('');
const observedEvents = ref(run.value?.events.length || 0);
const newEvents = computed(() => (run.value?.events.length || 0) > observedEvents.value);
watch(() => route.params.id, () => { observedEvents.value = run.value?.events.length || 0; });
async function cancel() { if (!run.value || busy.value) return; busy.value = true; error.value = ''; try { await api.cancelRun(run.value.id); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
function showNew() { observedEvents.value = run.value?.events.length || 0; document.getElementById('run-timeline-end')?.scrollIntoView({ block: 'end' }); }
</script>
<template>
  <div class="user-reading">
    <RouterLink to="/today" class="user-back"><ArrowLeft :size="16" aria-hidden="true" />今日简报</RouterLink>
    <EmptyState v-if="!run" title="未找到整理记录"><RouterLink to="/today" class="button">返回今日简报</RouterLink></EmptyState>
    <template v-else>
      <header class="page-header"><div><h1>整理记录</h1><p class="meta">{{ formatDate(run.startedAt) }} · {{ run.elapsedSeconds }} 秒</p></div><Badge :status="run.status" /></header>
      <p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p>
      <div v-if="brief || ['queued', 'running', 'cancelling'].includes(run.status)" class="run-actions"><RouterLink v-if="brief" class="button button--primary" :to="`/briefs/${brief.id}`">阅读简报<ArrowUpRight :size="16" aria-hidden="true" /></RouterLink><button v-if="['queued', 'running', 'cancelling'].includes(run.status)" class="button" :disabled="busy || run.status === 'cancelling'" @click="cancel"><Square :size="14" aria-hidden="true" />{{ busy || run.status === 'cancelling' ? '正在取消…' : '取消整理' }}</button></div>
      <p v-if="run.status === 'partial'" class="alert">部分完成，已有内容可阅读。</p>
      <p v-if="run.status === 'failed'" class="alert alert--danger">整理失败，可返回今日简报重试。</p>
      <p v-if="run.status === 'cancelled'" class="alert">已取消，现有简报已保留。</p>
      <div v-if="newEvents" class="new-events"><button class="button button--ghost" @click="showNew">查看新进度</button></div>
      <ol class="reader-timeline" aria-label="整理进度"><li v-for="event in run.events" :key="event.id"><span class="event-time">{{ event.time }}</span><details><summary>{{ event.title }}</summary><p>{{ event.detail }}</p></details><Badge :status="event.status" /></li></ol>
      <p v-if="!run.events.length" class="meta" role="status">等待开始…</p>
      <div id="run-timeline-end"></div>
    </template>
  </div>
</template>
<style scoped>
.run-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
.new-events { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.reader-timeline { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--color-border); }
.reader-timeline li { display: grid; grid-template-columns: 72px minmax(0, 1fr) auto; align-items: baseline; gap: 16px; padding: 16px 0; border-bottom: 1px solid var(--color-border); }
.event-time { color: var(--color-text-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.reader-timeline summary { min-height: 44px; padding-block: 10px; font-size: 14px; cursor: pointer; }
.reader-timeline p { color: var(--color-text-secondary); font-size: 13px; line-height: 22px; margin: 4px 0 0; overflow-wrap: anywhere; }
@media (max-width: 480px) { .reader-timeline li { grid-template-columns: minmax(0, 1fr) auto; column-gap: 12px; row-gap: 0; } .event-time { grid-column: 1 / -1; } }
</style>
