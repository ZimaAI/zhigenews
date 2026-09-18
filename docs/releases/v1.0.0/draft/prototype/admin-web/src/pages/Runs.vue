<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft, Square, FileText, Play } from 'lucide-vue-next';
import { state, api, formatDate, notify } from '@shared/mock';
import Badge from '@shared/Badge.vue';
import EmptyState from '@shared/EmptyState.vue';
import RunTimeline from '@shared/RunTimeline.vue';
const route = useRoute(); const router = useRouter(); const busy = ref(false); const error = ref('');
const search = computed({ get: () => String(route.query.q || ''), set: value => router.replace({ query: { ...route.query, q: value || undefined } }) });
const status = computed({ get: () => String(route.query.status || 'all'), set: value => router.replace({ query: { ...route.query, status: value === 'all' ? undefined : value } }) });
const model = computed({ get: () => String(route.query.model || 'all'), set: value => router.replace({ query: { ...route.query, model: value === 'all' ? undefined : value } }) });
const date = computed({ get: () => String(route.query.date || ''), set: value => router.replace({ query: { ...route.query, date: value || undefined } }) });
const run = computed(() => state.runs.find(r => r.id === route.params.id));
const filtered = computed(() => state.runs.filter(r => (status.value === 'all' || r.status === status.value) && (model.value === 'all' || r.model === model.value) && (!date.value || r.startedAt.startsWith(date.value)) && `${r.userName} ${r.id}`.toLowerCase().includes(search.value.toLowerCase())));
const models = computed(() => [...new Set(state.runs.map(r => r.model))]);
const canCancel = computed(() => run.value && ['running', 'queued'].includes(run.value.status));
const config = computed(() => state.configs.find(c => c.version === run.value?.configVersion));
const brief = computed(() => state.briefs.find(b => b.runId === run.value?.id));
async function cancel() { if (!run.value) return; busy.value = true; error.value = ''; try { await api.cancelRun(run.value.id); notify('示例运行已确认取消，已有简报仍可阅读。'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
async function simulate() { busy.value = true; error.value = ''; try { const id = await api.generateBrief(); router.push(`/runs/${id}`); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
</script>
<template>
  <template v-if="route.params.id"><RouterLink class="admin-back" :to="{ path: '/runs', query: route.query }"><ArrowLeft :size="16" />全部运行</RouterLink>
    <template v-if="run"><header class="page-header"><div><div class="eyebrow">RUN TRACE · SYNTHETIC</div><h1>{{ run.userName }}的每日简报</h1><p class="meta mono">{{ run.id }} · {{ formatDate(run.startedAt) }}</p></div><div class="actions"><Badge :status="run.status" /><button v-if="canCancel || run.status === 'cancelling'" class="button" :disabled="busy || run.status === 'cancelling'" @click="cancel"><Square :size="14" />{{ busy || run.status === 'cancelling' ? '正在取消…' : '取消运行' }}</button></div></header>
      <p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p><p v-if="run.status === 'partial'" class="alert">本次示例运行部分完成：可用内容已保留，部分来源未能完成，详见事件记录。</p>
      <section class="card"><div class="admin-run-meta"><div><span class="meta">耗时</span><strong>{{ run.elapsedSeconds }} 秒</strong></div><div><span class="meta">输入 / 输出 Token</span><strong>{{ run.inputTokens.toLocaleString() }} / {{ run.outputTokens.toLocaleString() }}</strong></div><div><span class="meta">示例费用</span><strong>${{ run.cost.toFixed(3) }}</strong></div><div><span class="meta">搜索次数</span><strong>{{ run.searchCount }}</strong></div></div><p class="admin-note">以上为固定演示值，失败运行的 0 用量不代表实际零计费；真实后端需报告已知用量与未知状态。</p></section>
      <details class="card admin-section"><summary>运行配置快照与访问边界</summary><dl class="admin-kv"><dt>模型 / 配置</dt><dd>{{ run.model }} / {{ run.configVersion }}</dd><dt>线程标识</dt><dd class="mono">thread:{{ run.id }}</dd><dt>来源虚拟挂载</dt><dd class="mono">/rss · /newsnow（只读）</dd><dt>工作目录</dt><dd class="mono">/workspace（本次用户运行专属）</dd><dt>文件一致性</dt><dd>读取记录 SHA-256；写入前比较最新版本</dd><dt>历史配置</dt><dd>{{ config ? `模型 ${config.maxModelCalls} 次 / 工具 ${config.maxToolCalls} 次 / 超时 ${config.maxSeconds} 秒` : '历史配置仅保留版本引用，完整参数尚未载入示例' }}</dd></dl><p class="meta">仅显示授权的参数摘要；密钥、账户地址和模型私有思考不进入事件详情。</p></details>
      <section class="admin-section"><div class="section-heading"><h2>事件与子任务</h2><span class="meta">按事件 ID 回放 · 逐项展开参数</span></div><RunTimeline :run="run" technical /></section>
      <section v-if="brief" class="card admin-section"><div class="row"><FileText :size="18" /><h2>生成产物</h2><Badge :status="brief.generationStatus" /></div><p>{{ brief.title }} · 内容 v{{ brief.version }}</p><p class="meta">{{ brief.items.length }} 条 synthetic 内容；邮件状态单独追踪。</p><RouterLink to="/deliveries">查看投递记录 →</RouterLink></section>
    </template><EmptyState v-else title="找不到这次运行" description="示例可能已经重置，请返回列表选择其他运行。"><RouterLink class="button" to="/runs">返回运行列表</RouterLink></EmptyState>
  </template>
  <template v-else><header class="page-header"><div><div class="eyebrow">AGENT OBSERVABILITY</div><h1>运行观察</h1><p class="muted">从一次简报，追溯模型、工具与子任务的实际事件。</p></div><button class="button" :disabled="busy" @click="simulate"><Play :size="16" />{{ busy ? '正在创建…' : '发起模拟运行' }}</button></header><p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p>
    <div class="admin-toolbar"><label class="field">用户或运行 ID<input v-model="search" class="field-control" placeholder="搜索本地运行样例"></label><label class="field">状态<select v-model="status" class="field-control"><option value="all">全部状态</option><option value="queued">排队中</option><option value="running">运行中</option><option value="completed">已完成</option><option value="partial">部分完成</option><option value="failed">失败</option><option value="cancelled">已取消</option></select></label><label class="field">模型<select v-model="model" class="field-control"><option value="all">全部模型</option><option v-for="item in models" :key="item" :value="item">{{ item }}</option></select></label><label class="field">运行日期<input v-model="date" class="field-control" type="date"></label></div>
    <div v-if="search || status !== 'all' || model !== 'all' || date" class="actions"><span class="meta">{{ filtered.length }} 条匹配记录</span><button class="button button--ghost" @click="router.replace({ query: {} })">清除筛选</button></div>
    <EmptyState v-if="!filtered.length" :title="state.runs.length ? '没有匹配的运行' : '还没有运行记录'" description="可清除筛选，或从用户端模拟生成第一份简报。" />
    <template v-else><p class="admin-scroll-hint">表格可左右滚动，运行名称可打开详情。</p><div class="table-wrap"><table class="data-table admin-table"><thead><tr><th>运行 / 用户</th><th>状态</th><th>模型 / 版本</th><th>开始时间</th><th>耗时 / Token</th><th>示例费用</th></tr></thead><tbody><tr v-for="item in filtered" :key="item.id"><td class="wide-cell"><RouterLink :to="{ path: `/runs/${item.id}`, query: route.query }">{{ item.userName }}的每日简报</RouterLink><small class="mono">{{ item.id }}</small></td><td><Badge :status="item.status" /></td><td>{{ item.model }}<small>{{ item.configVersion }}</small></td><td class="nowrap">{{ formatDate(item.startedAt) }}</td><td class="nowrap">{{ item.elapsedSeconds }} 秒<small>{{ (item.inputTokens + item.outputTokens).toLocaleString() }} Token</small></td><td>${{ item.cost.toFixed(3) }}</td></tr></tbody></table></div><p class="meta">{{ filtered.length }} 次 synthetic 运行 · 费用与用量为固定样例</p></template>
  </template>
</template>
