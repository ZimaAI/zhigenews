<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue';
import { Activity, RefreshCw, Settings2, ShieldAlert, ShieldCheck } from 'lucide-vue-next';
import { ApiError, type AnonymousAccount, type AnonymousPolicy, type AbuseEvent } from '@zhigenews/api-client';
import EmptyState from '@ui/EmptyState.vue';
import Modal from '@ui/Modal.vue';
import { request, errorText, formatDate, notify, useDirty, type Page } from '../lib';

const busy = ref('');
const retryAt = ref(0), now = ref(Date.now());
const remaining = computed(() => Math.max(0, Math.ceil((retryAt.value - now.value) / 1000)));
const retryTimer = setInterval(() => { now.value = Date.now(); }, 1000);
function failure(error: unknown) {
  if (error instanceof ApiError && error.status === 429) retryAt.value = Date.now() + Math.max(1, error.retryAfter ?? 60) * 1000;
  return errorText(error);
}

// Accounts and events paginate independently; a failure keeps the last successful page.
function paged<T extends { id: string }>(operation: string) {
  const items = shallowRef<T[]>([]), cursor = ref<string | null>(null);
  const loading = ref(false), loaded = ref(false), error = ref(''), refreshedAt = ref('');
  let controller: AbortController | undefined;
  async function load(more = false) {
    if (loading.value || remaining.value || (more && !cursor.value)) return;
    controller = new AbortController();
    loading.value = true; error.value = '';
    try {
      const page = await request<Page<T>>(operation, { query: { limit: 50, cursor: more ? cursor.value : undefined }, signal: controller.signal });
      items.value = more ? [...items.value, ...page.items.filter(item => !items.value.some(old => old.id === item.id))] : page.items;
      cursor.value = page.nextCursor; loaded.value = true; refreshedAt.value = new Date().toISOString();
    } catch (exception) { if (!controller.signal.aborted) error.value = failure(exception); }
    finally { loading.value = false; }
  }
  onBeforeUnmount(() => controller?.abort());
  return { items, cursor, loading, loaded, error, refreshedAt, load };
}
const accountList = paged<AnonymousAccount>('listAnonymousAccounts');
const { items: accounts, cursor: accountCursor, loading: accountsLoading, loaded: accountsLoaded, error: accountError, refreshedAt } = accountList;
const eventList = paged<AbuseEvent>('listAbuseEvents');
const { items: events, cursor: eventCursor, loading: eventsLoading, loaded: eventsLoaded, error: eventError } = eventList;
const policy = ref<AnonymousPolicy | null>(null), policyLoading = ref(false), policyLoadError = ref('');
const controller = new AbortController();
const loading = computed(() => accountsLoading.value || eventsLoading.value || policyLoading.value);
const search = ref(''), statusFilter = ref('all'), riskFilter = ref('all');
const hasFilters = computed(() => !!search.value.trim() || statusFilter.value !== 'all' || riskFilter.value !== 'all');
const users = computed(() => accounts.value.filter(account =>
  (statusFilter.value === 'all' || account.status === statusFilter.value) &&
  (riskFilter.value === 'all' || account.risk === riskFilter.value) &&
  `${account.name} ${account.id} ${account.ipLabel}`.toLowerCase().includes(search.value.trim().toLowerCase())));
const metrics = computed(() => ({
  watch: accounts.value.filter(account => account.risk !== 'normal').length,
  blocked: accounts.value.filter(account => account.status === 'blocked').length,
  rateLimited: accounts.value.reduce((total, account) => total + account.rateLimitHits, 0),
}));
const selectedId = ref('');
const selected = computed(() => accounts.value.find(account => account.id === selectedId.value));
const accountEvents = computed(() => events.value.filter(event => event.accountId === selectedId.value));
const reason = ref(''), originalReason = ref(''), reasonError = ref('');
const reasonInput = ref<HTMLTextAreaElement>();
const actionError = ref(''), actionResult = ref('');
const reasonDirty = computed(() => !!selectedId.value && reason.value !== originalReason.value);
const riskLabel = (risk: AnonymousAccount['risk']) => ({ normal: '正常', watch: '需关注', high: '高风险' })[risk];
const riskTone = (risk: AnonymousAccount['risk']) => ({ normal: 'success', watch: 'warning', high: 'danger' })[risk];
const eventLabel = (kind: AbuseEvent['kind']) => ({ rate_limited: '请求限流', account_blocked: '账户封禁', account_unblocked: '解除封禁', generation_rejected: '生成/策略审计' })[kind];

const policyOpen = ref(false), policyForm = ref<AnonymousPolicy | null>(null), originalPolicy = ref('');
const policyError = ref(''), policyResult = ref('');
const policyErrors = ref<Partial<Record<keyof AnonymousPolicy, string>>>({});
const policyFormElement = ref<HTMLFormElement>();
const policyFields: { key: keyof AnonymousPolicy; label: string; unit: string; max: number }[] = [
  { key: 'requestsPerMinute', label: '每个账户的请求上限', unit: '次 / 分钟', max: 600 },
  { key: 'generationsPerDay', label: '每个账户的生成上限', unit: '次 / 天', max: 100 },
  { key: 'maxConcurrentGenerations', label: '每个账户的并发生成上限', unit: '个', max: 10 },
  { key: 'accountsPerIpHour', label: '同一 IP 的新账户上限', unit: '个 / 小时', max: 100 },
];
const policyDirty = computed(() => !!policyForm.value && JSON.stringify(policyForm.value) !== originalPolicy.value);
useDirty(computed(() => policyDirty.value || reasonDirty.value));

async function loadPolicy() {
  if (policyLoading.value || remaining.value) return;
  policyLoading.value = true; policyLoadError.value = '';
  try {
    const value = await request<AnonymousPolicy>('getAnonymousPolicy', { signal: controller.signal });
    policy.value = value;
    if (!policyDirty.value) { policyForm.value = { ...value }; originalPolicy.value = JSON.stringify(value); }
  } catch (exception) { if (!controller.signal.aborted) policyLoadError.value = failure(exception); }
  finally { policyLoading.value = false; }
}
async function refresh() {
  if (busy.value || remaining.value) return;
  await Promise.all([accountList.load(), eventList.load(), loadPolicy()]);
}
function clearFilters() { search.value = ''; statusFilter.value = 'all'; riskFilter.value = 'all'; }
function inspect(account: AnonymousAccount) {
  selectedId.value = account.id;
  reason.value = account.status === 'blocked' ? '管理员解除封禁' : '';
  originalReason.value = reason.value; reasonError.value = ''; actionError.value = ''; actionResult.value = '';
}
function closeAccount() {
  if (busy.value) return;
  if (reasonDirty.value && !window.confirm('有未提交的处理原因，确定放弃并关闭吗？')) return;
  selectedId.value = ''; reason.value = ''; originalReason.value = '';
}
async function changeStatus() {
  const account = selected.value;
  if (!account || busy.value || remaining.value) return;
  reasonError.value = ''; actionError.value = ''; actionResult.value = '';
  const trimmed = reason.value.trim();
  if (!trimmed || trimmed.length > 200) {
    reasonError.value = '请填写 1–200 个字符的处理原因。';
    await nextTick(); reasonInput.value?.focus(); return;
  }
  const status = account.status === 'active' ? 'blocked' : 'active';
  busy.value = 'status';
  try {
    const updated = await request<AnonymousAccount>('setAnonymousAccountStatus', { path: { id: account.id }, body: { status, reason: trimmed } });
    accounts.value = accounts.value.map(item => item.id === updated.id ? updated : item);
    reason.value = status === 'blocked' ? '管理员解除封禁' : ''; originalReason.value = reason.value;
    actionResult.value = status === 'blocked' ? '账户已封禁，后续访问与新任务将被拒绝。已有内容保留。' : '已解除封禁，后续请求仍按账户和 IP 配额检查。';
    notify(status === 'blocked' ? '账户已封禁。' : '已解除封禁。');
    await eventList.load();
  } catch (exception) {
    actionError.value = failure(exception);
    if (exception instanceof ApiError && exception.fields?.reason) reasonError.value = exception.fields.reason;
  } finally { busy.value = ''; }
}
function editPolicy() {
  if (!policy.value || busy.value) return;
  if (!policyDirty.value) { policyForm.value = { ...policy.value }; originalPolicy.value = JSON.stringify(policy.value); }
  policyOpen.value = true;
}
function closePolicy() { if (!busy.value) policyOpen.value = false; }
function discardPolicy() {
  if (busy.value || !policy.value) return;
  policyForm.value = { ...policy.value }; originalPolicy.value = JSON.stringify(policy.value);
  policyErrors.value = {}; policyError.value = ''; policyResult.value = ''; policyOpen.value = false;
}
async function savePolicy() {
  if (!policyForm.value || busy.value || remaining.value) return;
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
    const updated = await request<AnonymousPolicy>('saveAnonymousPolicy', { body: { ...policyForm.value } });
    policy.value = updated; policyForm.value = { ...updated }; originalPolicy.value = JSON.stringify(updated);
    policyResult.value = '策略已保存，后续请求按新上限检查。'; notify('匿名账户防护策略已保存。');
    await eventList.load();
  } catch (exception) {
    policyError.value = failure(exception);
    if (exception instanceof ApiError && exception.fields) {
      for (const field of policyFields) if (exception.fields[field.key]) policyErrors.value[field.key] = exception.fields[field.key];
    }
  } finally { busy.value = ''; }
}
onMounted(refresh);
onBeforeUnmount(() => { controller.abort(); clearInterval(retryTimer); });
</script>

<template>
  <header class="page-header">
    <div><div class="eyebrow">ANONYMOUS ACCOUNTS</div><h1>匿名账户监测</h1><p>查看匿名账户的使用情况、风险和处理记录，调整后续请求的使用上限。</p></div>
    <div class="actions"><button class="button" :disabled="loading || !!busy || remaining > 0" @click="refresh"><RefreshCw :size="16" aria-hidden="true" />{{ loading ? '刷新中…' : '刷新' }}</button><button class="button button--primary" :disabled="!policy || !!busy" @click="editPolicy"><Settings2 :size="16" aria-hidden="true" />防护策略<span v-if="policyDirty" aria-label="有未保存的修改"> ·</span></button></div>
  </header>
  <p v-if="remaining" class="alert" role="status">请求受到限流，{{ remaining }} 秒后可重试。已保留页面数据与编辑草稿。</p>
  <p v-if="accountError" class="alert alert--danger" role="alert"><span>{{ accountError }}<template v-if="accountsLoaded"> 已保留上次账户数据。</template></span><button class="button" :disabled="accountsLoading || remaining > 0" @click="accountList.load()">重试账户列表</button></p>
  <p v-if="policyLoadError" class="alert alert--danger" role="alert"><span>防护策略读取失败：{{ policyLoadError }}<template v-if="policy"> 当前展示上次取得的策略。</template></span><button class="button" :disabled="policyLoading || remaining > 0" @click="loadPolicy">重试策略</button></p>
  <section v-if="accountsLoading && !accountsLoaded" class="skeleton" role="status" aria-label="正在加载匿名账户"></section>
  <EmptyState v-else-if="!accountsLoaded" title="账户列表暂不可用" :description="accountError || '请重试加载账户。'" error />
  <template v-else>
    <p class="meta monitor-scope">已加载 {{ accounts.length }} 个账户{{ accountCursor ? '，仍有更多记录' : '' }} · {{ formatDate(refreshedAt) }} 更新 · 时间：Asia/Shanghai</p>
    <div class="metric-grid" aria-label="已加载账户统计">
      <div class="metric"><span class="meta">已加载账户</span><strong>{{ accounts.length }}</strong></div>
      <div class="metric"><span class="meta">需关注 / 高风险</span><strong>{{ metrics.watch }}</strong></div>
      <div class="metric"><span class="meta">已封禁</span><strong>{{ metrics.blocked }}</strong></div>
      <div class="metric"><span class="meta">累计限流命中</span><strong>{{ metrics.rateLimited }}</strong></div>
    </div>
    <div class="admin-toolbar">
      <label class="field">查找已加载账户<input v-model="search" class="field-control" type="search" placeholder="账户 ID、名称或脱敏来源"></label>
      <label class="field">账户状态<select v-model="statusFilter" class="field-control"><option value="all">全部状态</option><option value="active">可用</option><option value="blocked">已封禁</option></select></label>
      <label class="field">风险状态<select v-model="riskFilter" class="field-control"><option value="all">全部风险</option><option value="normal">正常</option><option value="watch">需关注</option><option value="high">高风险</option></select></label>
      <button v-if="hasFilters" class="button" @click="clearFilters">清除筛选</button>
    </div>
    <p class="meta" role="status">显示 {{ users.length }} / {{ accounts.length }} 个已加载账户；筛选及上方统计仅覆盖已加载记录。</p>
    <EmptyState v-if="!accounts.length" title="还没有匿名账户" description="用户首次进入网站后，账户会出现在这里。" />
    <EmptyState v-else-if="!users.length" title="已加载记录中没有匹配账户" description="调整筛选条件，或加载更多账户。"><button class="button" @click="clearFilters">清除筛选</button></EmptyState>
    <template v-else>
      <p class="admin-scroll-hint">表格可左右滚动。</p>
      <div class="table-wrap" tabindex="0" role="region" aria-label="匿名账户列表，可横向滚动">
        <table class="data-table admin-table account-table"><thead><tr><th scope="col">匿名账户</th><th scope="col">状态 / 风险</th><th scope="col">最近活跃</th><th scope="col" class="number-cell">请求 / 分钟</th><th scope="col" class="number-cell">今日生成 / 并发</th><th scope="col" class="number-cell">限流命中</th><th scope="col">操作</th></tr></thead>
          <tbody><tr v-for="account in users" :key="account.id">
            <td class="wide-cell"><strong>{{ account.name }}</strong><small class="mono">{{ account.id }}</small><small>{{ account.ipLabel }}</small></td>
            <td><div class="account-badges"><span class="badge" :class="account.status === 'blocked' ? 'badge--danger' : 'badge--success'">{{ account.status === 'blocked' ? '已封禁' : '可用' }}</span><span class="badge" :class="`badge--${riskTone(account.risk)}`">{{ riskLabel(account.risk) }}</span></div></td>
            <td class="nowrap">{{ formatDate(account.lastSeenAt) }}</td><td class="number-cell">{{ account.requestsLastMinute }}</td><td class="number-cell">{{ account.generationsToday }}<small>并发 {{ account.activeGenerations }}</small></td><td class="number-cell">{{ account.rateLimitHits }}</td>
            <td><button class="button" :aria-label="`查看 ${account.name} 的账户详情`" @click="inspect(account)">查看详情</button></td>
          </tr></tbody>
        </table>
      </div>
    </template>
    <div class="admin-pagination"><span class="meta">{{ accountCursor ? '还有未加载的账户' : '已到列表末尾' }}</span><button v-if="accountCursor" class="button" :disabled="accountsLoading || remaining > 0" @click="accountList.load(true)">{{ accountsLoading ? '加载中…' : '加载更多账户' }}</button></div>
  </template>

  <section class="card admin-section" aria-labelledby="audit-heading">
    <div class="section-heading"><h2 id="audit-heading"><Activity :size="18" aria-hidden="true" />异常与管理审计</h2><button class="button" :disabled="eventsLoading || remaining > 0 || !!busy" @click="eventList.load()"><RefreshCw :size="16" aria-hidden="true" />刷新记录</button></div>
    <p class="meta">按后台返回顺序展示已加载的 {{ events.length }} 条记录{{ eventCursor ? '，仍有更多' : '' }}；时间为 Asia/Shanghai。</p>
    <p v-if="eventError" class="alert alert--danger" role="alert">{{ eventError }}<template v-if="eventsLoaded"> 已保留上次记录。</template></p>
    <div v-if="eventsLoading && !eventsLoaded" class="skeleton" role="status" aria-label="正在加载审计记录"></div>
    <p v-else-if="!eventsLoaded" class="muted">审计记录暂不可用，请重试刷新。</p>
    <p v-else-if="!events.length" class="muted">暂无异常或管理员操作记录。</p>
    <ul v-if="events.length" class="admin-list audit-list"><li v-for="event in events" :key="event.id"><div class="event-summary"><span class="badge" :class="event.kind === 'account_unblocked' ? 'badge--success' : 'badge--warning'">{{ eventLabel(event.kind) }}</span><time :datetime="event.time" class="meta">{{ formatDate(event.time) }}</time></div><p>{{ event.detail }}</p><button v-if="accounts.some(account => account.id === event.accountId)" class="button button--ghost audit-account mono" @click="inspect(accounts.find(account => account.id === event.accountId)!)">{{ event.accountId }}</button><span v-else class="meta mono">{{ event.accountId }}</span></li></ul>
    <div v-if="eventCursor" class="admin-pagination"><span class="meta">加载更早的记录</span><button class="button" :disabled="eventsLoading || remaining > 0" @click="eventList.load(true)">{{ eventsLoading ? '加载中…' : '加载更多记录' }}</button></div>
  </section>

  <Modal :open="!!selectedId" :title="selected?.name || '匿名账户详情'" @close="closeAccount">
    <template v-if="selected">
      <p class="meta mono">{{ selected.id }}</p>
      <div class="account-badges"><span class="badge" :class="selected.status === 'blocked' ? 'badge--danger' : 'badge--success'">{{ selected.status === 'blocked' ? '已封禁' : '可用' }}</span><span class="badge" :class="`badge--${riskTone(selected.risk)}`">{{ riskLabel(selected.risk) }}</span></div>
      <dl class="admin-kv account-details"><dt>创建时间</dt><dd>{{ formatDate(selected.createdAt) }}</dd><dt>最近活跃</dt><dd>{{ formatDate(selected.lastSeenAt) }}</dd><dt>来源 IP（脱敏）</dt><dd>{{ selected.ipLabel }}</dd><dt>最近 1 分钟请求</dt><dd>{{ selected.requestsLastMinute }} / {{ policy?.requestsPerMinute ?? '—' }} 次</dd><dt>今日生成</dt><dd>{{ selected.generationsToday }} / {{ policy?.generationsPerDay ?? '—' }} 次</dd><dt>当前并发生成</dt><dd>{{ selected.activeGenerations }} / {{ policy?.maxConcurrentGenerations ?? '—' }} 个</dd><dt>同 IP 每小时新号上限</dt><dd>{{ policy?.accountsPerIpHour ?? '—' }} 个</dd><dt>累计限流命中</dt><dd>{{ selected.rateLimitHits }} 次</dd><dt>封禁原因</dt><dd>{{ selected.blockReason || '未封禁；限流及风险依据见下方已加载审计。' }}</dd></dl>
      <p class="meta">数据取得于 {{ formatDate(refreshedAt) }}；使用上限适用于全部匿名账户。</p>
      <p v-if="actionError" class="alert alert--danger" role="alert">{{ actionError }}</p><p v-if="actionResult" class="alert alert--success" role="status">{{ actionResult }}</p>
      <form id="account-status-form" class="admin-form" novalidate @submit.prevent="changeStatus"><label class="field" for="account-reason">{{ selected.status === 'active' ? '封禁原因' : '解除原因' }}<textarea id="account-reason" ref="reasonInput" v-model="reason" class="field-control" required maxlength="200" :disabled="!!busy" :aria-invalid="!!reasonError" aria-describedby="account-reason-error account-reason-help" placeholder="记录处理依据"></textarea><span v-if="reasonError" id="account-reason-error" class="field-error">{{ reasonError }}</span><span id="account-reason-help" class="meta">{{ selected.status === 'active' ? '封禁后拒绝后续访问与新任务，保留已有内容。' : '解除后仍受账户和 IP 配额限制。' }}</span></label></form>
      <section class="admin-section"><h3>已加载的账户审计</h3><p v-if="eventError" class="alert alert--danger" role="alert">{{ eventError }}</p><ul v-if="accountEvents.length" class="admin-list audit-list"><li v-for="event in accountEvents" :key="event.id"><div class="event-summary"><strong>{{ eventLabel(event.kind) }}</strong><time :datetime="event.time" class="meta">{{ formatDate(event.time) }}</time></div><p>{{ event.detail }}</p></li></ul><p v-else class="meta">{{ eventsLoaded ? '已加载记录中暂无此账户审计。' : '账户审计尚未加载。' }}</p><button v-if="eventCursor" class="button" :disabled="eventsLoading || remaining > 0" @click="eventList.load(true)">加载更早的审计</button></section>
    </template>
    <template #footer><button class="button" :disabled="!!busy" @click="closeAccount">关闭</button><button v-if="selected" class="button" :class="selected.status === 'active' ? 'button--danger' : 'button--primary'" type="submit" form="account-status-form" :disabled="!!busy || remaining > 0"><component :is="selected.status === 'active' ? ShieldAlert : ShieldCheck" :size="16" aria-hidden="true" />{{ busy === 'status' ? '处理中…' : remaining ? `${remaining} 秒后可重试` : selected.status === 'active' ? '封禁账户' : '解除封禁' }}</button></template>
  </Modal>

  <Modal :open="policyOpen" title="匿名账户防护策略" @close="closePolicy">
    <form v-if="policyForm" id="anonymous-policy-form" ref="policyFormElement" class="admin-form stack" novalidate @submit.prevent="savePolicy">
      <p class="meta">保存后对后续请求生效。额度在服务端检查，策略变更记录在管理审计中。</p>
      <p v-if="policyError" class="alert alert--danger" role="alert">{{ policyError }}</p><p v-if="policyResult && !policyDirty" class="alert alert--success" role="status">{{ policyResult }}</p>
      <label v-for="field in policyFields" :key="field.key" class="field" :for="`policy-${field.key}`">{{ field.label }}<div class="policy-input"><input :id="`policy-${field.key}`" v-model.number="policyForm[field.key]" class="field-control" type="number" min="1" :max="field.max" step="1" required inputmode="numeric" :disabled="!!busy" :aria-invalid="!!policyErrors[field.key]" :aria-describedby="`policy-help-${field.key}`"><span class="meta">{{ field.unit }}</span></div><span :id="`policy-help-${field.key}`" :class="policyErrors[field.key] ? 'field-error' : 'meta'">{{ policyErrors[field.key] || `1–${field.max}，正整数` }}</span></label>
      <p v-if="policyDirty" class="meta" role="status">有未保存的修改；关闭弹窗会在当前页面保留草稿，离开页面前会提醒。</p>
    </form>
    <template #footer><button class="button" :disabled="!!busy" @click="discardPolicy">{{ policyDirty ? '放弃修改' : '关闭' }}</button><button class="button button--primary" type="submit" form="anonymous-policy-form" :disabled="!!busy || !policyDirty || remaining > 0">{{ busy === 'policy' ? '保存中…' : remaining ? `${remaining} 秒后可重试` : '保存策略' }}</button></template>
  </Modal>
</template>

<style scoped>
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
</style>
