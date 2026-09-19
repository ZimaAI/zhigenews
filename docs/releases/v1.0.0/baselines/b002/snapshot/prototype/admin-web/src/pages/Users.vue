<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { Activity, FlaskConical, RefreshCw, Settings2, ShieldAlert, ShieldCheck } from 'lucide-vue-next';
import { anonymousAdminApi } from '@shared/anonymous';
import type { AnonymousAccount, AnonymousPolicy, AbuseEvent } from '@shared/anonymous';
import EmptyState from '@shared/EmptyState.vue';
import Modal from '@shared/Modal.vue';

const accounts = ref<AnonymousAccount[]>([]);
const events = ref<AbuseEvent[]>([]);
const policy = ref<AnonymousPolicy | null>(null);
const loading = ref(false);
const loaded = ref(false);
const loadError = ref('');
const refreshedAt = ref('');
const search = ref('');
const statusFilter = ref('all');
const riskFilter = ref('all');
const selectedId = ref('');
const selected = computed(() => accounts.value.find(account => account.id === selectedId.value));
const busy = ref('');
const actionError = ref('');
const actionResult = ref('');
const blockReason = ref('');
const reasonError = ref('');
const reasonInput = ref<HTMLTextAreaElement>();
const policyOpen = ref(false);
const policyInitialized = ref(false);
const policyForm = ref<AnonymousPolicy>({ requestsPerMinute: 0, generationsPerDay: 0, maxConcurrentGenerations: 0, accountsPerIpHour: 0 });
const policyErrors = ref<Partial<Record<keyof AnonymousPolicy, string>>>({});
const policyError = ref('');
const policyResult = ref('');
const policyFormElement = ref<HTMLFormElement>();
const policyFields: { key: keyof AnonymousPolicy; label: string; unit: string; max: number }[] = [
  { key: 'requestsPerMinute', label: '每个账户的请求上限', unit: '次 / 分钟', max: 600 },
  { key: 'generationsPerDay', label: '每个账户的生成上限', unit: '次 / 天', max: 100 },
  { key: 'maxConcurrentGenerations', label: '每个账户的并发生成上限', unit: '个', max: 10 },
  { key: 'accountsPerIpHour', label: '同一 IP 的新账户上限', unit: '个 / 小时', max: 100 },
];
const policyDirty = computed(() => !!policy.value && policyFields.some(field => policyForm.value[field.key] !== policy.value![field.key]));
const hasFilters = computed(() => !!search.value.trim() || statusFilter.value !== 'all' || riskFilter.value !== 'all');
const users = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  return accounts.value.filter(account =>
    (statusFilter.value === 'all' || account.status === statusFilter.value) &&
    (riskFilter.value === 'all' || account.risk === riskFilter.value) &&
    `${account.name} ${account.id} ${account.ipLabel}`.toLocaleLowerCase().includes(query));
});
const metrics = computed(() => ({
  watch: accounts.value.filter(account => account.risk !== 'normal').length,
  blocked: accounts.value.filter(account => account.status === 'blocked').length,
  rateLimited: accounts.value.reduce((total, account) => total + account.rateLimitHits, 0),
}));
const sortedEvents = computed(() => [...events.value].sort((a, b) => b.time.localeCompare(a.time)));
const recentEvents = computed(() => sortedEvents.value.slice(0, 20));
const accountEvents = computed(() => sortedEvents.value.filter(event => event.accountId === selectedId.value).slice(0, 5));
const riskLabel = (risk: AnonymousAccount['risk']) => ({ normal: '正常', watch: '需关注', high: '高风险' }[risk]);
const riskTone = (risk: AnonymousAccount['risk']) => ({ normal: 'success', watch: 'warning', high: 'danger' }[risk]);
const eventLabel = (kind: AbuseEvent['kind']) => ({ rate_limited: '请求限流', account_blocked: '账户封禁', account_unblocked: '解除封禁', generation_rejected: '生成被拒绝' }[kind]);
function time(value: string) {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date) : '—';
}
function clearFilters() { search.value = ''; statusFilter.value = 'all'; riskFilter.value = 'all'; }
async function sync() {
  const snapshot = await anonymousAdminApi.list();
  accounts.value = snapshot.users;
  events.value = snapshot.events;
  policy.value = snapshot.policy;
  refreshedAt.value = new Date().toISOString();
  loaded.value = true;
}
async function refresh() {
  if (loading.value) return;
  loading.value = true;
  loadError.value = '';
  try { await sync(); } catch (error) { loadError.value = (error as Error).message; }
  finally { loading.value = false; }
}
function inspect(account: AnonymousAccount) {
  selectedId.value = account.id;
  blockReason.value = '';
  reasonError.value = '';
  actionError.value = '';
  actionResult.value = '';
}
async function act(kind: 'status' | 'simulate') {
  const account = selected.value;
  if (!account || busy.value) return;
  actionError.value = '';
  actionResult.value = '';
  reasonError.value = '';
  if (kind === 'status' && account.status === 'active' && !blockReason.value.trim()) {
    reasonError.value = '请填写封禁原因。';
    await nextTick(); reasonInput.value?.focus(); return;
  }
  busy.value = kind;
  try {
    if (kind === 'simulate') {
      await anonymousAdminApi.simulateAbuse(account.id);
      actionResult.value = '模拟异常已触发，处理结果见账户状态与审计记录。';
    } else {
      await anonymousAdminApi.setStatus(account.id, account.status === 'active' ? 'blocked' : 'active', account.status === 'active' ? blockReason.value.trim() : '管理员解除封禁');
      actionResult.value = account.status === 'active' ? '账户已封禁，后续访问将被拒绝。' : '已解除封禁，账户可以继续使用用户端功能。';
      blockReason.value = '';
    }
    try { await sync(); } catch (error) { actionError.value = `操作已完成，刷新失败：${(error as Error).message}`; }
  } catch (error) { actionError.value = (error as Error).message; }
  finally { busy.value = ''; }
}
function editPolicy() {
  if (!policy.value) return;
  if (!policyInitialized.value || !policyDirty.value) policyForm.value = { ...policy.value };
  policyInitialized.value = true;
  policyOpen.value = true;
}
function discardPolicy() {
  if (policy.value) policyForm.value = { ...policy.value };
  policyErrors.value = {}; policyError.value = ''; policyResult.value = ''; policyOpen.value = false;
}
async function savePolicy() {
  if (busy.value) return;
  policyErrors.value = {}; policyError.value = ''; policyResult.value = '';
  for (const field of policyFields) {
    const value = policyForm.value[field.key];
    if (!Number.isInteger(value) || value < 1 || value > field.max) policyErrors.value[field.key] = `请输入 1–${field.max} 之间的整数。`;
  }
  if (Object.keys(policyErrors.value).length) {
    await nextTick(); policyFormElement.value?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus(); return;
  }
  busy.value = 'policy';
  try {
    await anonymousAdminApi.savePolicy({ ...policyForm.value });
    policy.value = { ...policyForm.value };
    policyResult.value = '策略已保存，后续请求按新上限检查。';
  } catch (error) { policyError.value = (error as Error).message; }
  finally { busy.value = ''; }
}
let refreshTimer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  void refresh();
  refreshTimer = setInterval(() => { if (document.visibilityState === 'visible' && !busy.value && !policyOpen.value && !selectedId.value) void refresh(); }, 15000);
});
onBeforeUnmount(() => { if (refreshTimer) clearInterval(refreshTimer); });
</script>

<template>
  <header class="page-header">
    <div><div class="eyebrow">ANONYMOUS ACCOUNTS</div><h1>匿名账户监测</h1><p>匿名账户拥有全部用户端功能权限。查看访问异常并调整使用上限。</p></div>
    <div class="actions"><button class="button" :disabled="loading || !!busy" @click="refresh"><RefreshCw :size="16" aria-hidden="true" />{{ loading ? '刷新中…' : '刷新' }}</button><button class="button button--primary" :disabled="!policy || !!busy" @click="editPolicy"><Settings2 :size="16" aria-hidden="true" />防护策略<span v-if="policyInitialized && policyDirty" aria-label="有未保存的修改"> ·</span></button></div>
  </header>
  <p class="alert account-demo"><FlaskConical :size="18" aria-hidden="true" /><span>原型演示：账户与异常操作仅用于本地演示，数据来自开发服务；策略不代表已部署的生产防护。</span></p>
  <section v-if="loading && !loaded" class="card" role="status" aria-label="正在加载匿名账户"><p class="muted">正在加载账户和审计记录…</p><div class="skeleton" aria-hidden="true"></div></section>
  <EmptyState v-else-if="loadError && !loaded" title="账户监测加载失败" :description="loadError" error><button class="button" :disabled="loading" @click="refresh">重试</button></EmptyState>
  <template v-else-if="loaded">
    <div v-if="loadError" class="alert alert--danger" role="alert"><span>{{ loadError }} 当前保留上次成功获取的数据。</span><button class="button" :disabled="loading" @click="refresh">重试刷新</button></div>
    <p class="meta monitor-scope">本地服务全部 {{ accounts.length }} 个账户 · {{ time(refreshedAt) }} 更新 · 时间：Asia/Shanghai</p>
    <div class="metric-grid" aria-label="全部账户统计">
      <div class="metric"><span class="meta">匿名账户</span><strong>{{ accounts.length }}</strong></div>
      <div class="metric"><span class="meta">需关注 / 高风险</span><strong>{{ metrics.watch }}</strong></div>
      <div class="metric"><span class="meta">已封禁</span><strong>{{ metrics.blocked }}</strong></div>
      <div class="metric"><span class="meta">累计限流命中</span><strong>{{ metrics.rateLimited }}</strong></div>
    </div>
    <div class="admin-toolbar">
      <label class="field">搜索匿名账户<input v-model="search" class="field-control" type="search" placeholder="账号 ID、名称或脱敏 IP"></label>
      <label class="field">账户状态<select v-model="statusFilter" class="field-control"><option value="all">全部状态</option><option value="active">可用</option><option value="blocked">已封禁</option></select></label>
      <label class="field">风险状态<select v-model="riskFilter" class="field-control"><option value="all">全部风险</option><option value="normal">正常</option><option value="watch">需关注</option><option value="high">高风险</option></select></label>
      <button v-if="hasFilters" class="button" @click="clearFilters">清除筛选</button>
    </div>
    <p class="meta" role="status">显示 {{ users.length }} / {{ accounts.length }} 个账户</p>
    <EmptyState v-if="!accounts.length" title="还没有匿名账户" description="用户首次进入网站后，账户会出现在这里。"><button class="button" :disabled="loading" @click="refresh">刷新账户</button></EmptyState>
    <EmptyState v-else-if="!users.length" title="没有匹配的账户" description="调整账号、状态或风险条件后重试。"><button class="button" @click="clearFilters">清除筛选</button></EmptyState>
    <template v-else>
      <p class="admin-scroll-hint">表格可左右滚动。</p>
      <div class="table-wrap" tabindex="0" role="region" aria-label="匿名账户列表，可横向滚动">
        <table class="data-table admin-table account-table"><thead><tr><th scope="col">匿名账户</th><th scope="col">状态 / 风险</th><th scope="col">最近活跃</th><th scope="col" class="number-cell">请求 / 分钟</th><th scope="col" class="number-cell">今日生成</th><th scope="col" class="number-cell">限流命中</th><th scope="col">操作</th></tr></thead>
          <tbody><tr v-for="account in users" :key="account.id">
            <td class="wide-cell"><strong>{{ account.name }}</strong><small class="mono">{{ account.id }}</small><small>{{ account.ipLabel }}</small></td>
            <td><div class="account-badges"><span class="badge" :class="account.status === 'blocked' ? 'badge--danger' : 'badge--success'">{{ account.status === 'blocked' ? '已封禁' : '可用' }}</span><span class="badge" :class="`badge--${riskTone(account.risk)}`">{{ riskLabel(account.risk) }}</span></div></td>
            <td class="nowrap">{{ time(account.lastSeenAt) }}</td><td class="number-cell">{{ account.requestsLastMinute }}</td><td class="number-cell">{{ account.generationsToday }}<small>并发 {{ account.activeGenerations }}</small></td><td class="number-cell">{{ account.rateLimitHits }}</td>
            <td><button class="button" :aria-label="`查看 ${account.name} 的账户详情`" @click="inspect(account)">查看详情</button></td>
          </tr></tbody>
        </table>
      </div>
    </template>
    <section class="card admin-section">
      <div class="section-heading"><h2><Activity :size="18" aria-hidden="true" />异常与审计记录</h2><span class="meta">最近 {{ recentEvents.length }} 条 / 共 {{ events.length }} 条</span></div>
      <p v-if="!events.length" class="muted">暂无异常或账户操作记录。</p>
      <ul v-else class="admin-list audit-list"><li v-for="event in recentEvents" :key="event.id"><div class="event-summary"><span class="badge" :class="event.kind === 'account_unblocked' ? 'badge--success' : 'badge--warning'">{{ eventLabel(event.kind) }}</span><time :datetime="event.time" class="meta">{{ time(event.time) }}</time></div><p>{{ event.detail }}</p><button v-if="accounts.some(account => account.id === event.accountId)" class="button button--ghost audit-account mono" @click="inspect(accounts.find(account => account.id === event.accountId)!)">{{ event.accountId }}</button><span v-else class="meta mono">{{ event.accountId }}</span></li></ul>
    </section>
  </template>

  <Modal :open="!!selectedId" :title="selected?.name || '匿名账户详情'" @close="selectedId = ''">
    <template v-if="selected">
      <p class="meta mono">{{ selected.id }}</p>
      <div class="account-badges"><span class="badge" :class="selected.status === 'blocked' ? 'badge--danger' : 'badge--success'">{{ selected.status === 'blocked' ? '已封禁' : '可用' }}</span><span class="badge" :class="`badge--${riskTone(selected.risk)}`">{{ riskLabel(selected.risk) }}</span><span class="badge">完整用户端权限</span></div>
      <dl class="admin-kv account-details"><dt>创建时间</dt><dd>{{ time(selected.createdAt) }}</dd><dt>最近活跃</dt><dd>{{ time(selected.lastSeenAt) }}</dd><dt>来源 IP（脱敏）</dt><dd>{{ selected.ipLabel }}</dd><dt>最近 1 分钟请求</dt><dd>{{ selected.requestsLastMinute }} / {{ policy?.requestsPerMinute }} 次</dd><dt>今日生成</dt><dd>{{ selected.generationsToday }} / {{ policy?.generationsPerDay }} 次</dd><dt>当前并发生成</dt><dd>{{ selected.activeGenerations }} / {{ policy?.maxConcurrentGenerations }} 个</dd><dt>累计限流命中</dt><dd>{{ selected.rateLimitHits }} 次</dd><dt>拦截原因</dt><dd>{{ selected.blockReason || '暂无账户封禁；限流详情见审计记录。' }}</dd></dl>
      <p class="meta">时间：Asia/Shanghai · 使用上限适用于全部匿名账户。</p>
      <p v-if="actionError" class="alert alert--danger" role="alert">{{ actionError }}</p><p v-if="actionResult" class="alert alert--success" role="status">{{ actionResult }}</p>
      <form v-if="selected.status === 'active'" id="block-account-form" @submit.prevent="act('status')">
        <label class="field">封禁原因<textarea ref="reasonInput" v-model="blockReason" class="field-control" maxlength="300" :aria-invalid="!!reasonError" :aria-describedby="reasonError ? 'block-reason-error block-reason-help' : 'block-reason-help'" placeholder="记录异常行为和处理依据"></textarea><span v-if="reasonError" id="block-reason-error" class="field-error">{{ reasonError }}</span><span id="block-reason-help" class="meta">封禁后拒绝该账户后续访问，已有订阅和简报保留。</span></label>
      </form>
      <section class="admin-section"><h3>最近账户记录</h3><ul v-if="accountEvents.length" class="admin-list audit-list"><li v-for="event in accountEvents" :key="event.id"><div class="event-summary"><strong>{{ eventLabel(event.kind) }}</strong><time :datetime="event.time" class="meta">{{ time(event.time) }}</time></div><p>{{ event.detail }}</p></li></ul><p v-else class="meta">暂无账户审计记录。</p></section>
      <p class="admin-note">“模拟异常”会向本地开发服务写入示例事件，并演示当前策略的处理结果。</p>
    </template>
    <template #footer><button class="button button--ghost" :disabled="!!busy || selected?.status !== 'active'" @click="act('simulate')"><FlaskConical :size="16" aria-hidden="true" />{{ busy === 'simulate' ? '模拟中…' : '模拟异常' }}</button><button v-if="selected?.status === 'active'" class="button button--danger" form="block-account-form" type="submit" :disabled="!!busy"><ShieldAlert :size="16" aria-hidden="true" />{{ busy === 'status' ? '处理中…' : '封禁账户' }}</button><button v-else-if="selected" class="button button--primary" :disabled="!!busy" @click="act('status')"><ShieldCheck :size="16" aria-hidden="true" />{{ busy === 'status' ? '处理中…' : '解除封禁' }}</button></template>
  </Modal>

  <Modal :open="policyOpen" title="匿名账户防护策略" @close="policyOpen = false">
    <form id="anonymous-policy-form" ref="policyFormElement" class="admin-form stack" novalidate @submit.prevent="savePolicy">
      <p class="meta">保存后对后续请求生效。超出使用上限会被拒绝，并写入审计记录。</p>
      <p v-if="policyError" class="alert alert--danger" role="alert">{{ policyError }}</p><p v-if="policyResult && !policyDirty" class="alert alert--success" role="status">{{ policyResult }}</p>
      <label v-for="field in policyFields" :key="field.key" class="field">{{ field.label }}<div class="policy-input"><input :id="`policy-${field.key}`" v-model.number="policyForm[field.key]" class="field-control" type="number" min="1" :max="field.max" step="1" inputmode="numeric" :aria-invalid="!!policyErrors[field.key]" :aria-describedby="`policy-help-${field.key}`"><span class="meta">{{ field.unit }}</span></div><span :id="`policy-help-${field.key}`" :class="policyErrors[field.key] ? 'field-error' : 'meta'">{{ policyErrors[field.key] || `1–${field.max}，正整数` }}</span></label>
      <p v-if="policyDirty" class="meta" role="status">有未保存的修改，关闭弹窗会在当前页面保留草稿。</p>
    </form>
    <template #footer><button class="button" :disabled="!!busy" @click="discardPolicy">{{ policyDirty ? '放弃修改' : '关闭' }}</button><button class="button button--primary" type="submit" form="anonymous-policy-form" :disabled="!!busy || !policyDirty">{{ busy === 'policy' ? '保存中…' : '保存策略' }}</button></template>
  </Modal>
</template>

<style scoped>
.account-demo { align-items: flex-start; justify-content: flex-start; }
.account-demo > svg { flex-shrink: 0; margin-top: 2px; }
.monitor-scope { margin-bottom: var(--space-3); }
.metric-grid .metric { min-width: 0; }
.account-table { min-width: 850px; }
.account-table .button { white-space: nowrap; }
.number-cell { text-align: right; font-variant-numeric: tabular-nums; }
.account-badges { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.account-table .account-badges { min-width: 6rem; }
.section-heading { flex-wrap: wrap; }
.section-heading h2 { display: inline-flex; align-items: center; gap: var(--space-2); }
.event-summary { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-2); }
.audit-list p { color: var(--color-text-secondary); font-size: var(--font-size-ui); overflow-wrap: anywhere; }
.audit-account { justify-content: flex-start; padding-inline: 0; min-height: var(--touch-target); font-size: var(--font-size-meta); max-width: 100%; white-space: normal; overflow-wrap: anywhere; text-align: left; }
.account-details { margin-block: var(--space-6); }
.policy-input { display: flex; align-items: center; gap: var(--space-3); }
.policy-input input { flex: 1; min-width: 0; }
.policy-input .meta { flex-shrink: 0; }
@media (max-width: 767px) { .account-demo { flex-direction: row; gap: var(--space-3); } }
</style>
