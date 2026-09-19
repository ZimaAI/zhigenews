<script setup lang="ts">
import { computed, ref } from 'vue';
import { ChevronDown, GitBranch, PlugZap } from 'lucide-vue-next';
import type { AgentRun } from './types';
import Badge from './Badge.vue';
const props = defineProps<{ run: AgentRun; technical?: boolean }>();
const disconnected = ref(false);
const frozenEvents = ref<AgentRun['events']>([]);
const visibleEvents = computed(() => disconnected.value ? frozenEvents.value : props.run.events);
function toggleConnection() { if (!disconnected.value) frozenEvents.value = JSON.parse(JSON.stringify(props.run.events)); disconnected.value = !disconnected.value; }
const message = computed(() => disconnected.value ? '连接暂时中断，任务状态待确认。已有事件仍保留。' : '示例事件回放 · 仅展示工具动作和结果，不展示模型私有思考');
</script>
<template>
  <div class="timeline-notice row"><p class="meta">{{ message }}</p><button class="button button--ghost" @click="toggleConnection"><PlugZap :size="16" />{{ disconnected ? '模拟重连' : '模拟断线' }}</button></div>
  <ol class="timeline" aria-label="Agent 示例事件时间线"><li v-for="event in visibleEvents" :key="event.id" class="timeline-event" :class="{ 'timeline-event--failed': event.status === 'failed' }"><span class="timeline-marker" aria-hidden="true"></span><div class="event-head"><span class="mono meta">{{ event.time }}</span><Badge :status="event.status" /><span class="meta">{{ event.duration }}</span></div><h3>{{ event.title }}</h3><p>{{ event.detail }}</p><details v-if="technical && (event.params || event.output || event.tool)" class="event-details"><summary><ChevronDown :size="14" aria-hidden="true" />{{ event.tool || '事件' }} · 参数与结果</summary><pre v-if="event.params">{{ event.params }}</pre><pre v-if="event.output">{{ event.output }}</pre></details></li></ol>
  <p v-if="!run.events.length" class="meta">等待第一条示例事件。</p>
  <section v-if="run.subtasks.length" class="subtasks"><h3 class="row"><GitBranch :size="18" /> 子任务</h3><div v-for="task in run.subtasks" :key="task.id" class="subtask row"><div><strong>{{ task.name }}</strong><p class="meta">{{ task.detail }}</p></div><Badge :status="task.status" /></div></section>
</template>
