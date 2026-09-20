<script setup lang="ts">
import type { SourceDeletionJob } from '@zhigenews/api-client';
defineProps<{ job: SourceDeletionJob | null; error: string; checked: boolean }>();
defineEmits<{ retry: [] }>();
const labels = { pending: '待处理', running: '正在删除', deleted: '已删除', skipped: '已跳过', failed: '失败', unprocessed: '未处理' };
</script>
<template>
  <section v-if="job || error || !checked" class="card source-result" aria-label="来源删除进度">
    <h2>来源删除进度</h2>
    <p v-if="!checked && !error" role="status">正在确认是否有删除任务…</p>
    <p v-if="error" class="alert alert--danger" role="alert">进度连接中断，任务状态待确认。{{ error }}<button class="button" @click="$emit('retry')">重新连接</button></p>
    <template v-if="job">
      <p role="status">{{ job.status === 'queued' ? '等待执行' : job.status === 'running' ? '正在删除' : job.status === 'failed' ? '任务已中断' : '处理完成' }} · 已处理 {{ job.processed }} / {{ job.total }} 项</p>
      <progress class="source-progress" :value="job.processed" :max="job.total || 1" aria-label="来源删除处理进度" />
      <p>已删除 {{ job.deleted }} 项 · 跳过 {{ job.skipped }} 项 · 失败 {{ job.failed }} 项</p>
      <p v-if="job.status === 'failed' && job.total > job.processed">另有 {{ job.total - job.processed }} 项尚未处理。</p>
      <p v-if="job.error" class="alert alert--danger">{{ job.error }}</p>
      <p v-if="['queued', 'running'].includes(job.status)" class="admin-note">离开页面后继续执行，返回可查看进度。当前任务结束前，所有管理员均不能再发起批量删除。</p>
      <details v-if="job.items.length" open><summary>本次来源明细（{{ job.total }} 项）</summary>
        <ul class="admin-list source-progress-items" tabindex="0" aria-label="来源删除结果明细"><li v-for="item in job.items" :key="item.id">
          <strong>{{ item.name }}</strong> <span class="badge" :class="item.status === 'deleted' ? 'badge--success' : item.status === 'failed' ? 'badge--danger' : item.status === 'skipped' ? 'badge--warning' : ''">{{ labels[item.status] }}</span>
          <p v-if="item.message">{{ item.message }}</p><small class="meta mono">{{ item.id }}</small>
        </li></ul>
      </details>
      <p v-else class="meta">本次没有符合条件的来源。</p>
    </template>
  </section>
</template>
