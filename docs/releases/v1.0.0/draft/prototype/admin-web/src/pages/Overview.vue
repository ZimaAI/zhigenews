<script setup lang="ts">
import { computed } from 'vue';
import { ArrowUpRight, Radio, Activity, Mail, ArrowRight } from 'lucide-vue-next';
import { state, formatDate } from '@shared/mock';
import Badge from '@shared/Badge.vue';
import EmptyState from '@shared/EmptyState.vue';
const active = computed(() => state.runs.filter(r => ['running', 'queued', 'cancelling'].includes(r.status)));
const issues = computed(() => state.sources.filter(s => ['failed', 'unverified'].includes(s.status)));
const failedDelivery = computed(() => state.deliveries.filter(d => ['failed', 'unknown'].includes(d.status)));
const published = computed(() => state.configs.find(c => c.status === 'published'));
</script>
<template>
  <header class="page-header"><div><div class="eyebrow">SYSTEM OVERVIEW</div><h1>让每份简报，按时抵达</h1><p class="muted">先看需要处理的事，再查看运行细节。</p></div><RouterLink class="button" to="/runs">查看全部运行 <ArrowUpRight :size="16" /></RouterLink></header>
  <div class="metric-grid">
    <div class="metric"><span class="meta">进行中的运行 · 示例</span><strong>{{ active.length }}</strong><span class="meta">{{ state.runs.length }} 次 synthetic 运行</span></div>
    <div class="metric"><span class="meta">可用新闻源 · 示例</span><strong>{{ state.sources.filter(s => s.status === 'healthy').length }}<small> / {{ state.sources.length }}</small></strong><span class="meta">RSS 与 NewsNow</span></div>
    <div class="metric"><span class="meta">需要关注的投递 · 示例</span><strong>{{ failedDelivery.length }}</strong><span class="meta">失败或尚无送达回执</span></div>
    <div class="metric"><span class="meta">当前 Agent 配置</span><strong>{{ published?.version || '—' }}</strong><span class="meta">{{ published ? '已发布 · 新运行使用' : '尚未发布配置' }}</span></div>
  </div>
  <div class="admin-grid admin-section">
    <section class="card"><div class="section-heading"><h2>需要关注</h2><span class="meta">synthetic 演示事件</span></div>
      <EmptyState v-if="!issues.length && !failedDelivery.length" title="目前没有待处理问题" description="此处根据来源与投递样例状态显示，不代表生产系统健康度。" />
      <ul v-else class="admin-list">
        <li v-for="source in issues" :key="source.id"><div class="row"><Radio :size="18" class="admin-mini-icon" /><h3>{{ source.name }}</h3><Badge :status="source.status" /></div><p class="muted">{{ source.error || '尚未完成来源验证，需要一次模拟同步。' }}</p><RouterLink class="admin-subtle-link" :to="`/sources/${source.id}`">检查来源与轮询设置 <ArrowRight :size="14" /></RouterLink></li>
        <li v-for="delivery in failedDelivery.slice(0, 2)" :key="delivery.id"><div class="row"><Mail :size="18" class="admin-mini-icon" /><h3>{{ delivery.userName }}的邮件</h3><Badge :status="delivery.status" /></div><p class="muted">{{ delivery.error || '提交状态待确认，没有邮件送达回执。' }}</p><RouterLink class="admin-subtle-link" to="/deliveries">查看投递记录 <ArrowRight :size="14" /></RouterLink></li>
      </ul>
    </section>
    <section class="card"><div class="section-heading"><h2>最近运行</h2><Activity :size="18" class="admin-mini-icon" /></div><EmptyState v-if="!state.runs.length" title="还没有运行记录" description="完成模型与 Agent 配置后，可从用户端模拟生成。" />
      <ul v-else class="admin-list"><li v-for="run in state.runs.slice(0, 4)" :key="run.id"><div class="row"><RouterLink :to="`/runs/${run.id}`">{{ run.userName }}的每日简报</RouterLink><Badge :status="run.status" /></div><p class="meta">{{ formatDate(run.startedAt) }} · {{ run.configVersion }}</p><p class="meta">{{ run.model }} · {{ run.elapsedSeconds }} 秒</p></li></ul>
      <RouterLink class="admin-subtle-link" to="/runs">查看完整运行列表</RouterLink>
    </section>
  </div>
  <section class="card admin-section"><div class="section-heading"><h2>开发者工作流</h2><span class="meta">配置 → 运行 → 评估</span></div><div class="admin-grid"><div><p class="muted">从可用模型开始，用独立版本调整工具预算、摘要与子 Agent 参数，再通过固定样例比较变化。</p><p class="meta">演示中的耗时、Token、费用及评分均为固定样例，不是实际模型测量结果。</p></div><div class="actions"><RouterLink class="button" to="/models">模型连接</RouterLink><RouterLink class="button" to="/agent-configs">Agent 参数</RouterLink><RouterLink class="button button--primary" to="/evaluations">比较评估结果 <ArrowRight :size="16" /></RouterLink></div></div></section>
</template>
