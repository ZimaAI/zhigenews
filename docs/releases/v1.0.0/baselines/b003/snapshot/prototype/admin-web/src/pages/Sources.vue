<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { Plus, RefreshCw, ArrowLeft, Pencil, ExternalLink, Rss, Radio } from 'lucide-vue-next';
import { state, api, notify, formatDate } from '@shared/mock';
import type { Source } from '@shared/types';
import Badge from '@shared/Badge.vue';
import Modal from '@shared/Modal.vue';
import EmptyState from '@shared/EmptyState.vue';
const route = useRoute();
const search = ref(''); const kind = ref('all'); const busy = ref(''); const error = ref(''); const editing = ref(false);
const selected = computed(() => state.sources.find(s => s.id === route.params.id));
const filtered = computed(() => state.sources.filter(s => (kind.value === 'all' || s.kind === kind.value) && `${s.name} ${s.sourceId}`.toLowerCase().includes(search.value.toLowerCase())));
const blank = (): Source => ({ id: '', name: '', kind: 'rss', sourceId: '', url: '', interval: 1800, upstreamInterval: 0, status: 'unverified', lastSuccess: '', nextFetch: '', lastChanged: '', items: 0, error: '' });
const form = ref<Source>(blank());
function edit(source?: Source) { form.value = source ? { ...source } : blank(); error.value = ''; editing.value = true; }
async function save() { busy.value = 'save'; error.value = ''; try { await api.saveSource({ ...form.value }); editing.value = false; notify('来源已保存，等待模拟验证。'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = ''; } }
async function action(source: Source, sync = false) { busy.value = source.id; error.value = ''; try { if (sync) { await api.fetchSource(source.id); if (source.status === 'failed') { error.value = source.error; return; } } else await api.toggleSource(source.id); notify(sync ? '已完成一次模拟同步，缓存状态已更新。' : '来源状态已更新。'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = ''; } }
</script>
<template>
  <template v-if="route.params.id">
    <RouterLink class="admin-back" to="/sources"><ArrowLeft :size="16" />全部新闻源</RouterLink>
    <template v-if="selected"><header class="page-header"><div><div class="eyebrow">SOURCE DETAIL · SYNTHETIC</div><h1>{{ selected.name }}</h1><p class="muted">采集节奏、最近结果与本地归档。</p></div><div class="actions"><button class="button" @click="edit(selected)"><Pencil :size="16" />编辑来源</button><button class="button button--primary" :disabled="!!busy || selected.status === 'disabled'" @click="action(selected, true)"><RefreshCw :size="16" />{{ busy === selected.id ? '模拟同步中…' : '模拟同步' }}</button></div></header>
      <p v-if="error && !editing" class="alert alert--danger" role="alert">{{ error }}</p>
      <div v-if="selected.error" class="alert alert--danger">{{ selected.error }}。可检查配置后重试模拟同步。</div>
      <div class="admin-grid admin-section"><section class="card"><div class="section-heading"><h2>采集配置</h2><Badge :status="selected.status" /></div><dl class="admin-kv"><dt>来源类型</dt><dd>{{ selected.kind === 'rss' ? 'RSS 订阅' : 'NewsNow 热榜' }}</dd><dt>来源标识</dt><dd class="mono">{{ selected.sourceId }}</dd><dt>接口地址</dt><dd><a :href="selected.url" target="_blank" rel="noopener noreferrer">{{ selected.url }} <ExternalLink :size="13" />（新标签页）</a></dd><dt>系统轮询间隔</dt><dd>{{ selected.interval }} 秒</dd><dt>上游更新间隔</dt><dd>{{ selected.upstreamInterval ? `${selected.upstreamInterval} 秒` : 'RSS 无上游声明，采用配置间隔' }}</dd><dt>最近成功</dt><dd>{{ selected.lastSuccess ? formatDate(selected.lastSuccess) : '尚无成功记录' }}</dd><dt>下次拉取</dt><dd>{{ selected.status === 'disabled' ? '已停用' : selected.nextFetch ? formatDate(selected.nextFetch) : '验证后安排' }}</dd><dt>最近内容变化</dt><dd>{{ selected.lastChanged ? formatDate(selected.lastChanged) : '尚无记录' }}</dd></dl></section><section class="card"><h2>本地缓存</h2><p class="muted">{{ selected.items }} 条 synthetic 新闻记录</p><p class="meta">下列为目录约定预览，不代表已在服务器抓取文件。</p><details class="admin-diff" open><summary>归档目录结构</summary><pre>{{ selected.kind }}/{{ selected.sourceId || 'source-id' }}/
├── latest.json
├── metadata.json
└── 2026/09/18/
    └── 08-00-00.{{ selected.kind === 'rss' ? 'xml' : 'json' }}</pre></details><p class="admin-note">Agent 仅通过只读虚拟目录访问采集内容；写入简报使用每次运行的独立工作目录。</p><button class="button" :disabled="!!busy" @click="action(selected)">{{ selected.status === 'disabled' ? '启用来源' : '停用来源' }}</button></section></div>
    </template><EmptyState v-else title="找不到这个来源" description="示例可能已重置，请返回新闻源列表。"><RouterLink class="button" to="/sources">返回列表</RouterLink></EmptyState>
  </template>
  <template v-else>
    <header class="page-header"><div><div class="eyebrow">NEWS SOURCES</div><h1>新闻源</h1><p class="muted">不同来源，不同采集节奏。为每次筛选留下可追溯的内容。</p></div><button class="button button--primary" @click="edit()"><Plus :size="16" />添加新闻源</button></header>
    <p v-if="error && !editing" class="alert alert--danger" role="alert">{{ error }}</p>
    <div class="admin-toolbar"><label class="field">搜索来源<input v-model="search" class="field-control" placeholder="名称或来源 ID"></label><label class="field">来源类型<select v-model="kind" class="field-control"><option value="all">全部类型</option><option value="rss">RSS 订阅</option><option value="newsnow">NewsNow 热榜</option></select></label><button v-if="search || kind !== 'all'" class="button" @click="search = ''; kind = 'all'">清除筛选</button></div>
    <EmptyState v-if="!filtered.length" :title="state.sources.length ? '没有匹配的来源' : '还没有新闻源'" description="添加 RSS 订阅或 NewsNow 来源，为 Agent 准备最新内容。"><button class="button" @click="edit()">添加来源</button></EmptyState>
    <template v-else><p class="admin-scroll-hint">表格可左右滚动，点击来源名称查看完整信息。</p><div class="table-wrap"><table class="data-table admin-table"><thead><tr><th>来源</th><th>状态</th><th>轮询间隔</th><th>最近成功 / 下次拉取</th><th>内容</th><th>操作</th></tr></thead><tbody><tr v-for="source in filtered" :key="source.id"><td class="wide-cell"><RouterLink :to="`/sources/${source.id}`">{{ source.name }}</RouterLink><small class="row"><Rss v-if="source.kind === 'rss'" :size="13" /><Radio v-else :size="13" />{{ source.kind === 'rss' ? 'RSS' : 'NewsNow' }} · {{ source.sourceId }}</small></td><td><Badge :status="source.status" /></td><td class="nowrap">{{ source.interval }} 秒<small v-if="source.upstreamInterval">上游 {{ source.upstreamInterval }} 秒</small></td><td class="nowrap">{{ source.lastSuccess ? formatDate(source.lastSuccess) : '尚无记录' }}<small>{{ source.status === 'disabled' ? '已停用' : source.nextFetch ? formatDate(source.nextFetch) : '等待验证' }}</small></td><td class="nowrap">{{ source.items }} 条</td><td><div class="actions"><button class="button button--ghost" :disabled="!!busy || source.status === 'disabled'" @click="action(source, true)">{{ busy === source.id ? '处理中…' : '同步' }}</button><button class="button button--ghost" @click="edit(source)">编辑</button><button class="button button--ghost" :disabled="!!busy" @click="action(source)">{{ source.status === 'disabled' ? '启用' : '停用' }}</button></div></td></tr></tbody></table></div><p class="meta">{{ filtered.length }} 个来源 · 采集和状态均为 synthetic 示例</p></template>
    <section class="card admin-section"><h2>Agent 自主搜索</h2><p class="muted">Tavily 作为 web_search 工具按需调用，不进入新闻源轮询。调用次数由 Agent 配置中的预算控制。</p><RouterLink to="/agent-configs">管理 Agent 工具与预算</RouterLink></section>
  </template>
  <Modal :open="editing" :title="form.id ? '编辑新闻源' : '添加新闻源'" @close="editing = false">
    <form id="source-form" class="admin-form stack" @submit.prevent="save">
      <p v-if="error" class="alert alert--danger admin-error" role="alert">{{ error }}</p>
      <label class="field">来源名称<input v-model="form.name" class="field-control" required maxlength="80" placeholder="例如：Hugging Face Blog"></label>
      <div class="form-grid"><label class="field">来源类型<select v-model="form.kind" class="field-control"><option value="rss">RSS 订阅</option><option value="newsnow">NewsNow 热榜</option></select></label><label class="field">来源 ID<input v-model="form.sourceId" class="field-control" :required="form.kind === 'newsnow'" pattern="[a-zA-Z0-9_-]+" placeholder="RSS 可留空自动分配"><span class="meta">NewsNow 填上游 ID；仅字母、数字、短横线或下划线。</span></label></div>
      <label class="field">{{ form.kind === 'rss' ? 'RSS 订阅地址' : 'NewsNow API 地址' }}<input v-model="form.url" class="field-control" required type="url" placeholder="https://example.com/feed.xml"></label>
      <div class="form-grid"><label class="field">轮询间隔（秒）<input v-model.number="form.interval" class="field-control" type="number" :min="Math.max(60, form.upstreamInterval)" max="86400" required><span class="meta">范围 60–86400 秒；不短于上游声明间隔。</span></label><label v-if="form.kind === 'newsnow'" class="field">上游更新间隔（秒）<input v-model.number="form.upstreamInterval" class="field-control" type="number" min="60" max="86400" required></label></div>
      <p class="admin-note">仅模拟保存与解析，不会向外部站点发起采集。</p>
    </form><template #footer><button class="button" :disabled="busy === 'save'" @click="editing = false">取消</button><button class="button button--primary" form="source-form" type="submit" :disabled="busy === 'save'">{{ busy === 'save' ? '正在保存…' : '保存来源' }}</button></template>
  </Modal>
</template>
