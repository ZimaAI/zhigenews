<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { ArrowLeft, Plus, RefreshCw, Pencil, Pause, Play } from 'lucide-vue-next';
import { ApiError } from '@zhigenews/api-client';
import type { Source, SourceWrite, SourceBatchResult, SourceDeletionJob } from '@zhigenews/api-client';
import Modal from '@ui/Modal.vue';
import EmptyState from '@ui/EmptyState.vue';
import { request, errorText, formatDate, notify, useDirty, useRefresh, intentKeys } from '../lib';
import { useSourceList } from '../source-list';
import { useSourceDeletion } from '../source-deletion';
import SourceDeletionProgress from '../components/SourceDeletionProgress.vue';
const route = useRoute();
const collection = useSourceList();
const deletion = useSourceDeletion();
const { job, error: progressError, checked: progressChecked, unavailable: deletionUnavailable, pendingIds } = deletion;
const selectionPending = computed(() => [...collection.selectedIds.value].some(id => pendingIds.value.has(id)));
const pending = (source: Source) => pendingIds.value.has(source.id);
const { items, loading, refreshing, loaded, error: loadError, search, selectedIds, page, total, totalPages, invalidTotal, allSelected } = collection;
const selected = ref<Source | null>(null), detailLoading = ref(false), detailError = ref('');
const busy = ref(''), actionError = ref(''), editing = ref(false), editId = ref(''), formError = ref('');
const jump = ref<number | string>(1), pageError = ref('');
const batchResult = ref<SourceBatchResult | null>(null), batchLabel = ref('');
const deleteDialog = ref<'selected' | 'invalid' | null>(null), deleteIds = ref<string[]>([]), deleteCount = ref(0), deleteError = ref('');
const emptyForm = (): SourceWrite => ({ name: '', kind: 'rss', sourceId: '', url: '', interval: 3600 });
const form = ref<SourceWrite>(emptyForm()), initialForm = ref('');
const formVersion = ref(0), conflictSource = ref<Source | null>(null);
const dirty = computed(() => editing.value && JSON.stringify(form.value) !== initialForm.value);
const confirmDiscard = useDirty(dirty), keys = intentKeys();
const enabled = (source: Source) => source.enabled ?? source.status !== 'disabled';
const collecting = (source: Source) => ['queued', 'running', 'stopping'].includes(source.collectionStatus || '') || source.status === 'syncing';
const healthLabel = (source: Source) => ({ healthy: '正常', failed: '采集失败 · 待重试', invalid: '失效', unverified: '未验证' }[source.health || 'unverified']);
const collectionLabel = (source: Source) => ({ idle: '', queued: '已排队', running: '采集中', stopping: '停止中', stopped: '已停止' }[source.collectionStatus || 'idle']);
function edit(source?: Source) {
  if (source && pending(source)) return;
  formVersion.value = source?.version ?? 0; conflictSource.value = null;
  editId.value = source?.id || '';
  form.value = source ? { name: source.name, kind: source.kind, sourceId: source.sourceId, url: source.url, interval: source.interval } : emptyForm();
  initialForm.value = JSON.stringify(form.value); formError.value = ''; editing.value = true;
}
function close() { if (!busy.value && confirmDiscard()) { editing.value = false; formError.value = ''; } }
async function save() {
  if (busy.value) return;
  if (pendingIds.value.has(editId.value)) { formError.value = '来源正在等待或执行删除，请查看删除进度。'; return; }
  busy.value = 'save'; formError.value = ''; invalidateReads();
  try {
    const source = await request<Source>(editId.value ? 'saveSource' : 'createSource', { path: editId.value ? { id: editId.value } : undefined, body: { ...form.value, ...(editId.value ? { version: formVersion.value } : {}), name: form.value.name.trim(), sourceId: form.value.sourceId.trim(), url: form.value.url.trim() } });
    if (selected.value?.id === source.id) selected.value = source;
    editing.value = false; void collection.refresh(); notify('来源已保存。');
  } catch (error) {
    formError.value = errorText(error);
    if (error instanceof ApiError && error.status === 404) formError.value = '该来源已被删除或不可访问，草稿已保留。';
    if (error instanceof ApiError && error.code === 'VERSION_CONFLICT') {
      try { conflictSource.value = await request<Source>('getSource', { path: { id: editId.value } }); }
      catch (readError) { formError.value = errorText(readError); }
    }
  } finally { busy.value = ''; }
}
async function saveReviewedDraft() {
  if (!conflictSource.value) return;
  formVersion.value = conflictSource.value.version ?? 0; conflictSource.value = null;
  await save();
}
async function act(source: Source, operation: 'fetchSource' | 'setSourceEnabled' | 'stopSource') {
  if (busy.value) return;
  if (pending(source)) return;
  busy.value = source.id; actionError.value = ''; invalidateReads();
  try {
    const updated = await request<Source>(operation, { path: { id: source.id }, ...(operation === 'fetchSource' ? { idempotencyKey: keys.get(source.id) } : operation === 'setSourceEnabled' ? { body: { enabled: !enabled(source) } } : {}) });
    collection.replace(updated); if (selected.value?.id === updated.id) selected.value = updated;
    if (operation === 'fetchSource') { keys.done(source.id); notify('手动采集已排队，请等待实际结果。'); }
    else if (operation === 'stopSource') notify(updated.collectionStatus === 'stopped' ? '采集已停止，来源已停用。' : '已请求停止并停用来源，确认停止后才可删除。');
    else notify(enabled(updated) ? '来源已启用。' : '来源已停用，正在进行的采集需另行停止。');
    void collection.refresh();
  } catch (error) { actionError.value = errorText(error); } finally { busy.value = ''; }
}
function askDelete(mode: 'selected' | 'invalid') {
  if (deletionUnavailable.value) return;
  keys.done('delete');
  deleteIds.value = [...selectedIds.value]; deleteCount.value = mode === 'invalid' ? invalidTotal.value : deleteIds.value.length;
  deleteError.value = ''; deleteDialog.value = mode;
}
async function batch(action: 'disable' | 'delete') {
  if (busy.value || (action === 'delete' && deletionUnavailable.value)) return;
  const allInvalid = action === 'delete' && deleteDialog.value === 'invalid';
  busy.value = 'batch'; actionError.value = ''; deleteError.value = ''; invalidateReads();
  try {
    if (action === 'delete') {
      const result = await request<SourceDeletionJob>(allInvalid ? 'deleteInvalidSources' : 'batchSources', {
        idempotencyKey: keys.get('delete'), ...(allInvalid ? {} : { body: { action, ids: deleteIds.value } }),
      });
      deletion.accept(result); keys.done('delete'); deleteDialog.value = null;
      notify('删除任务已提交，离开页面后仍会继续执行。');
    } else {
      const result = await request<SourceBatchResult>('batchSources', { body: { action, ids: [...selectedIds.value] } });
      batchResult.value = result; batchLabel.value = '停用'; collection.forget(result.succeeded);
    }
    void collection.refresh();
  } catch (error) {
    if (action === 'delete') { deleteError.value = errorText(error); void deletion.poll(); } else actionError.value = errorText(error);
  } finally { busy.value = ''; }
}
async function go(target: number) {
  pageError.value = '';
  if (!Number.isInteger(target) || target < 1 || target > totalPages.value) { pageError.value = `请输入 1 到 ${totalPages.value} 之间的整数页码。`; return; }
  await collection.load(target);
}
watch(page, value => { jump.value = value; });
let detailRevision = 0;
function invalidateReads() { collection.invalidate(); detailRevision++; detailLoading.value = false; }
async function loadDetail() {
  const id = String(route.params.id || ''); if (!id) { selected.value = null; return; }
  const revision = ++detailRevision; detailLoading.value = true; detailError.value = '';
  try { const source = await request<Source>('getSource', { path: { id } }); if (revision === detailRevision) selected.value = source; }
  catch (error) { if (revision === detailRevision) detailError.value = errorText(error); }
  finally { if (revision === detailRevision) detailLoading.value = false; }
}
watch(() => route.params.id, () => { detailRevision++; selected.value = null; void loadDetail(); }, { immediate: true });
onMounted(() => { void collection.load(); void deletion.poll(); });
watch(job, (value, previous) => {
  if (!value) return;
  collection.remove(value.items.filter(item => item.status === 'deleted').map(item => item.id));
  if (value.id !== previous?.id || value.processed !== previous?.processed) {
    if (!busy.value) void collection.refresh();
  }
});
useRefresh(() => deletion.poll(false), 1000);
useRefresh(() => { if (busy.value || editing.value || deleteDialog.value || loading.value || detailLoading.value) return; return route.params.id ? loadDetail() : collection.refresh(); }, 5000);
</script>
<template>
  <template v-if="route.params.id"><RouterLink class="admin-back" to="/sources"><ArrowLeft :size="16" />全部新闻来源</RouterLink><div v-if="detailLoading && !selected" class="skeleton" role="status" aria-label="加载来源详情"></div><EmptyState v-else-if="!selected" title="无法加载这个来源" :description="detailError || '来源不存在或已不可访问。'" error><button class="button" @click="loadDetail">重试</button></EmptyState>
    <template v-if="selected"><header class="page-header"><div><div class="eyebrow">SOURCE DETAIL</div><h1>{{ selected.name }}</h1><p>RSS · {{ selected.sourceId || selected.id }}</p></div><div class="actions"><span class="badge" :class="selected.health === 'invalid' ? 'badge--danger' : 'badge--primary'">{{ healthLabel(selected) }}</span><span class="badge">{{ enabled(selected) ? '已启用' : '已停用' }} {{ collectionLabel(selected) }}</span><button class="button" :disabled="!!busy || pending(selected)" @click="edit(selected)"><Pencil :size="16" />编辑来源</button><button class="button button--primary" :disabled="!!busy || pending(selected) || collecting(selected) || (!enabled(selected) && selected.health !== 'invalid')" @click="act(selected, 'fetchSource')"><RefreshCw :size="16" />{{ busy === selected.id ? '正在提交…' : '请求采集' }}</button></div></header>
      <p v-if="actionError || detailError" class="alert alert--danger" role="alert">{{ actionError || detailError }}</p><p v-if="selected.error" class="alert alert--danger">{{ selected.error }}</p><p v-if="selected.stale" class="alert">{{ selected.snapshotId ? '缓存已过期，现有快照仍保留。请查看采集状态。' : '尚无有效快照，等待首次成功采集。' }}</p>
      <div class="metric-grid"><div class="metric"><span class="meta">当前条目</span><strong>{{ selected.items }}</strong></div><div class="metric"><span class="meta">有效采集周期</span><strong>{{ selected.interval }} <small>秒</small></strong></div><div class="metric"><span class="meta">快照年龄</span><strong>{{ selected.cacheAgeSeconds ?? '—' }} <small v-if="selected.cacheAgeSeconds != null">秒</small></strong></div></div>
      <section class="card"><h2>连接与快照</h2><dl class="admin-kv"><dt>请求地址</dt><dd><a :href="selected.url" target="_blank" rel="noopener noreferrer">{{ selected.url }}</a></dd><dt>来源标识</dt><dd class="mono">{{ selected.id }}</dd><dt>最近尝试</dt><dd>{{ formatDate(selected.lastFetchedAt) }}</dd><dt>最近成功</dt><dd>{{ formatDate(selected.lastSuccess) }}</dd><dt>下次采集</dt><dd>{{ formatDate(selected.nextFetch) }}</dd><dt>内容变化</dt><dd>{{ formatDate(selected.lastChanged) }}</dd><dt>快照取得时间</dt><dd>{{ formatDate(selected.snapshotFetchedAt) }}</dd><dt>快照 ID</dt><dd class="mono">{{ selected.snapshotId || '尚无快照' }}</dd><dt>缓存状态</dt><dd>{{ selected.stale ? '待更新' : '有效' }}</dd></dl><button v-if="collecting(selected)" class="button button--danger" :disabled="!!busy || pending(selected) || selected.collectionStatus === 'stopping'" @click="act(selected, 'stopSource')">{{ selected.collectionStatus === 'stopping' ? '停止中…' : '停止采集并停用' }}</button><p class="admin-note">条件请求未发现变化时继续使用原快照；最近成功时间与快照内容取得时间分别记录。</p><button class="button" :disabled="!!busy || pending(selected)" @click="act(selected, 'setSourceEnabled')"><component :is="!enabled(selected) ? Play : Pause" :size="16" />{{ !enabled(selected) ? '启用来源' : '停用来源' }}</button></section>
    </template>
  </template>

  <template v-else>
    <header class="page-header"><div><div class="eyebrow">NEWS SOURCES</div><h1>新闻来源</h1><p>按名称搜索 RSS 订阅来源，管理采集与失效状态。</p></div><div class="actions"><button class="button" :disabled="loading || !!busy" @click="collection.load()"><RefreshCw :size="16" />刷新</button><button class="button button--primary" @click="edit()"><Plus :size="16" />添加来源</button></div></header>
    <SourceDeletionProgress :job="job" :error="progressError" :checked="progressChecked" @retry="deletion.poll()" />
    <p v-if="actionError || loadError" class="alert alert--danger" role="alert">{{ actionError || loadError }}{{ loaded ? ' 已保留上次数据。' : '' }}<button v-if="loadError" class="button" :disabled="loading" @click="collection.load()">重试加载</button></p>
    <section v-if="batchResult" class="card source-result" aria-live="polite"><h2>{{ batchLabel }}结果</h2><p>已{{ batchLabel }} {{ batchResult.succeeded.length }} 条，未完成 {{ batchResult.failed.length }} 条。</p><ul v-if="batchResult.failed.length"><li v-for="failure in batchResult.failed" :key="failure.id"><RouterLink :to="`/sources/${failure.id}`">查看未完成来源</RouterLink>：{{ failure.message }}</li></ul><p v-if="batchResult.failed.some(item => item.code === 'SOURCE_BUSY')" class="meta">先打开来源停止采集，确认已停止后再重试删除。</p></section>
    <form class="admin-toolbar" @submit.prevent="pageError = ''; collection.applyFilters()">
      <label class="field">来源名称<input v-model="search" class="field-control" type="search" placeholder="仅按名称搜索全部来源" :disabled="!!busy"></label>
      <button class="button button--primary" type="submit" :disabled="loading || !!busy">搜索</button>
    </form>
    <div class="actions source-batch"><span aria-live="polite">已选 {{ selectedIds.size }} 条</span><button class="button" :disabled="!selectedIds.size || selectionPending || !!busy || loading" @click="batch('disable')">停用所选来源</button><button class="button button--danger" :disabled="!selectedIds.size || deletionUnavailable || !!busy || loading" @click="askDelete('selected')">删除所选来源</button><button class="button button--danger" :disabled="!loaded || !invalidTotal || deletionUnavailable || !!busy || loading" @click="askDelete('invalid')">删除全部失效来源（{{ invalidTotal }}）</button><button v-if="selectedIds.size" class="button button--ghost" :disabled="!!busy" @click="selectedIds = new Set()">清空选择</button></div>
    <p class="admin-note">翻页保留选择；更换搜索会清空选择。“全部失效来源”覆盖数据库全部来源，包含已停用项。</p>
    <p v-if="refreshing || (loading && loaded)" role="status" class="meta">正在更新来源列表…</p>
    <div v-if="loading && !loaded" class="skeleton" role="status" aria-label="加载来源列表"></div>
    <EmptyState v-else-if="!items.length" :error="!!loadError" :title="loadError ? '来源列表暂不可用' : collection.filtered.value ? '没有匹配的来源' : '尚无新闻来源'" :description="loadError || '添加新闻来源，或调整名称和类型筛选。'" />
    <div v-else class="table-wrap" tabindex="0" role="region" aria-label="新闻来源列表，可横向滚动" :aria-busy="loading"><table class="data-table admin-table source-table"><thead><tr><th><label class="source-check"><input type="checkbox" :checked="allSelected" :indeterminate="!allSelected && items.some(item => selectedIds.has(item.id))" :disabled="loading || !!busy" @change="collection.togglePage()"><span>本页</span></label></th><th>来源</th><th>健康 / 采集状态</th><th>采集周期</th><th>最近成功 / 下次采集</th><th>操作</th></tr></thead><tbody>
      <tr v-for="source in items" :key="source.id"><td><label class="source-check"><input type="checkbox" :aria-label="`选择 ${source.name}`" :checked="selectedIds.has(source.id)" :disabled="loading || !!busy" @change="collection.toggle(source.id)"></label></td><td class="wide-cell"><RouterLink :to="`/sources/${source.id}`">{{ source.name }}</RouterLink><small>RSS</small><small>{{ source.sourceId || source.url }}</small><small>{{ enabled(source) ? '已启用' : '已停用' }}</small></td>
      <td><span class="badge" :class="source.health === 'invalid' ? 'badge--danger' : source.health === 'failed' ? 'badge--warning' : source.health === 'healthy' ? 'badge--success' : ''">{{ healthLabel(source) }}</span><small v-if="collectionLabel(source)" role="status">{{ collectionLabel(source) }}</small><small>{{ source.items }} 条 · {{ source.stale ? '待更新' : '缓存有效' }}</small></td>
      <td>{{ source.interval }} 秒</td><td>{{ formatDate(source.lastSuccess) }}<small>{{ formatDate(source.nextFetch) }}</small></td>
      <td><div class="actions"><button class="button button--small" :disabled="!!busy || pending(source) || collecting(source)" @click="edit(source)">编辑</button><button class="button button--small" :disabled="!!busy || pending(source) || collecting(source) || (!enabled(source) && source.health !== 'invalid')" @click="act(source, 'fetchSource')">{{ source.health === 'invalid' ? '手动重试' : '采集' }}</button><button class="button button--small" :disabled="!!busy || pending(source) || source.collectionStatus === 'stopping'" @click="act(source, 'setSourceEnabled')">{{ enabled(source) ? '停用' : '启用' }}</button><button v-if="collecting(source)" class="button button--small button--danger" :disabled="!!busy || pending(source) || source.collectionStatus === 'stopping'" @click="act(source, 'stopSource')">{{ source.collectionStatus === 'stopping' ? '停止中…' : '停止采集' }}</button></div><small v-if="pending(source)" role="status">等待或正在删除</small><small v-if="source.error">{{ source.error }}</small></td></tr>
    </tbody></table></div>
    <nav class="admin-pagination" aria-label="来源分页"><span class="meta" aria-live="polite">共 {{ total }} 条 · 每页 10 条 · 第 {{ totalPages ? page : 0 }} / {{ totalPages }} 页</span><div class="actions"><button class="button" :disabled="loading || !!busy || page <= 1" @click="go(page - 1)">上一页</button><button class="button" :disabled="loading || !!busy || page >= totalPages" @click="go(page + 1)">下一页</button><form class="actions" @submit.prevent="go(Number(jump))"><label class="source-jump">跳至<input v-model="jump" class="field-control" type="number" min="1" :max="totalPages || 1" step="1" required aria-label="跳转页码" :aria-invalid="!!pageError" aria-describedby="source-page-error" :disabled="!totalPages || loading || !!busy">页</label><button class="button" type="submit" :disabled="!totalPages || loading || !!busy">跳转</button></form></div></nav>
    <p v-if="pageError" id="source-page-error" class="field-error" role="alert">{{ pageError }}</p>
  </template>
  <Modal :open="!!deleteDialog" :title="deleteDialog === 'invalid' ? '删除全部失效来源' : '删除所选来源'" @close="!busy && (deleteDialog = null)"><p>将删除 {{ deleteCount }} 条{{ deleteDialog === 'invalid' ? '失效来源（包含已停用项，不受搜索或分页限制）' : '已选来源' }}及其历史快照、采集记录和采集文件。</p><p class="alert alert--danger">删除后不能恢复。已有简报内容与原文链接保留，但快照无法查看、关联评估样例无法重跑，正在生成的简报可能失败。</p><p>仍在采集的来源不会删除。请先停止采集，确认已停止后再重试。执行时会重新核实状态并显示实际结果。提交后在后台执行，可离开页面后返回查看进度。</p><p v-if="deleteError" class="alert alert--danger" role="alert">{{ deleteError }}</p><template #footer><button class="button" :disabled="!!busy" @click="deleteDialog = null">取消</button><button class="button button--danger" :disabled="!!busy || deletionUnavailable" @click="batch('delete')">{{ busy ? '正在提交…' : '确认删除' }}</button></template></Modal>
  <Modal :open="editing" :title="editId ? '编辑新闻来源' : '添加新闻来源'" @close="close"><form id="source-form" class="admin-form stack" @submit.prevent="save"><p v-if="formError" class="alert alert--danger" role="alert">{{ formError }}</p><section v-if="conflictSource" class="card"><h3>请核对服务器上的最新配置</h3><p>你的草稿已保留。以下配置可能由其他管理员更新：</p><dl class="admin-kv"><dt>名称</dt><dd>{{ conflictSource.name }}</dd><dt>类型 / 标识</dt><dd>{{ conflictSource.kind }} / {{ conflictSource.sourceId || '—' }}</dd><dt>地址</dt><dd>{{ conflictSource.url }}</dd><dt>采集周期</dt><dd>{{ conflictSource.interval }} 秒</dd></dl><button type="button" class="button" :disabled="!!busy || pendingIds.has(editId)" @click="saveReviewedDraft">已核对，使用当前草稿保存</button></section><p v-if="pendingIds.has(editId)" class="alert">该来源正在等待或执行删除，草稿已保留，暂时不能保存。</p><label class="field">名称<input v-model="form.name" class="field-control" required maxlength="120"></label><div class="form-grid"><label class="field">本地采集周期（秒）<input v-model.number="form.interval" class="field-control" type="number" min="1" step="1" required></label></div><label class="field">来源标识（可选）<input v-model="form.sourceId" class="field-control" placeholder="来源提供的稳定标识"></label><label class="field">RSS 地址<input v-model="form.url" class="field-control" type="url" required placeholder="https://"></label><p class="meta">仅支持 RSS / Atom 订阅。有效采集周期会遵循订阅提供的 TTL，HTTP 缓存和失败退避可能延后下次采集。</p></form><template #footer><button class="button" :disabled="!!busy" @click="close">取消</button><button class="button button--primary" form="source-form" type="submit" :disabled="!!busy || !!conflictSource || pendingIds.has(editId)">{{ busy === 'save' ? '保存中…' : '保存来源' }}</button></template></Modal>
</template>
