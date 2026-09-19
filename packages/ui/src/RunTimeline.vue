<script setup lang="ts">
import { ChevronDown, GitBranch } from 'lucide-vue-next';
import type { AgentRun } from '@zhigenews/api-client';
import Badge from './Badge.vue';
import { formatDate } from './format';
defineProps<{ run: AgentRun; technical?: boolean }>();
</script>

<template>
  <ol class="timeline" aria-label="运行事件时间线">
    <li v-for="event in run.events" :key="event.id" class="timeline-event" :class="{ 'timeline-event--failed': event.status === 'failed' }">
      <span class="timeline-marker" aria-hidden="true"></span>
      <div class="event-head"><time class="mono meta" :datetime="event.time">{{ formatDate(event.time, true) }}</time><Badge :status="event.status" /><span class="meta">{{ event.duration }}</span></div>
      <h3>{{ event.title }}</h3><p>{{ event.detail }}</p>
      <details v-if="technical && (event.params || event.output || event.tool)" class="event-details">
        <summary><ChevronDown :size="14" aria-hidden="true" />{{ event.tool || '事件' }} · 参数与结果</summary>
        <pre v-if="event.params">{{ event.params }}</pre><pre v-if="event.output">{{ event.output }}</pre>
      </details>
    </li>
  </ol>
  <p v-if="!run.events.length" class="meta">尚无运行事件。</p>
  <section v-if="run.subtasks.length" class="subtasks"><h3 class="row"><GitBranch :size="18" aria-hidden="true" />子任务</h3><div v-for="task in run.subtasks" :key="task.id" class="subtask row"><div><strong>{{ task.name }}</strong><p class="meta">{{ task.detail }}</p></div><Badge :status="task.status" /></div></section>
</template>
