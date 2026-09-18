<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { ArrowLeft, Square, ArrowUpRight } from 'lucide-vue-next';
import { api, state, formatDate } from '@shared/mock';
import Badge from '@shared/Badge.vue';
import EmptyState from '@shared/EmptyState.vue';
import RunTimeline from '@shared/RunTimeline.vue';
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
    <RouterLink to="/today" class="user-back"><ArrowLeft :size="16" aria-hidden="true" />返回今日简报</RouterLink>
    <EmptyState v-if="!run" title="未找到这次整理记录" description="当前场景中没有这次运行，或它不属于当前演示读者。请回到自己的简报重新打开。"><RouterLink to="/today" class="button">查看今日简报</RouterLink></EmptyState>
    <template v-else>
      <header class="page-header"><div><p class="eyebrow">BEHIND YOUR BRIEF</p><h1>简报整理过程</h1><p class="muted">只展示已发生的模拟事件，不展示模型私有思考。</p></div><Badge :status="run.status" /></header>
      <p v-if="error" class="alert alert--danger" role="alert">{{ error }} 可重试对应操作。</p>
      <section class="card run-summary"><dl class="user-key-values"><dt>开始时间</dt><dd>{{ formatDate(run.startedAt) }}</dd><dt>已运行</dt><dd>{{ run.elapsedSeconds }} 秒（演示）</dd><dt>本次任务</dt><dd class="mono">{{ run.id }}</dd></dl><div class="run-actions"><RouterLink v-if="brief" class="button button--primary" :to="`/briefs/${brief.id}`">阅读本期简报<ArrowUpRight :size="16" aria-hidden="true" /></RouterLink><button v-if="['queued', 'running', 'cancelling'].includes(run.status)" class="button" :disabled="busy || run.status === 'cancelling'" @click="cancel"><Square :size="14" aria-hidden="true" />{{ busy || run.status === 'cancelling' ? '正在取消…' : '取消本次整理' }}</button></div></section>
      <p v-if="run.status === 'partial'" class="alert">这次整理部分完成。已有内容可阅读，缺失与限制记录在下面的事件中。</p>
      <p v-if="run.status === 'failed'" class="alert alert--danger">本次整理未完成。现有简报不受影响，请检查失败事件后从今日页面重新生成。</p>
      <p v-if="run.status === 'cancelled'" class="alert">本次整理已取消。现有简报与历史记录保留。</p>
      <div class="section-heading"><h2>事件时间线</h2><button v-if="newEvents" class="button button--ghost" @click="showNew">查看新事件</button><span v-else class="meta">示例回放 · 不代表真实执行</span></div>
      <RunTimeline :run="run" :technical="false" /><div id="run-timeline-end"></div>
    </template>
  </div>
</template>
<style scoped>
.run-summary { margin-bottom: 24px; }
.run-summary dl { margin: 0; }
.run-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--color-border); }
.connection-alert { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.connection-alert > div { flex: 1; min-width: 0; }
.connection-alert strong { font-size: 14px; }
.connection-alert p { font-size: 13px; margin: 4px 0 0; }
.section-heading { margin-top: 32px; }
.section-heading h2 { font-size: 20px; }
</style>
