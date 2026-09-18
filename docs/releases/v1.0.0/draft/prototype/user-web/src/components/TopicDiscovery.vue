<script setup lang="ts">
import { computed, ref } from 'vue';
import { Check, Compass, Cpu, FileText, Layers, LayoutGrid, Plus, ScanEye, Search, X } from 'lucide-vue-next';
import EmptyState from '@shared/EmptyState.vue';
import { TOPICS } from '@shared/mock';

const props = defineProps<{ modelValue: string[]; error?: string; disabled?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [topics: string[]] }>();
const query = ref('');
const category = ref('all');
const filters = [
  { id: 'all', name: '全部主题', icon: Compass },
  { id: 'technology', name: '技术与模型', icon: Cpu },
  { id: 'applications', name: '产品与应用', icon: Layers },
];
const details = [
  { name: 'Agent 工程', category: 'applications', image: '/images/topic-agent.png', description: '让智能体走进实际工作流', keywords: 'agent langgraph 工具 编排 工作流', icon: Layers },
  { name: '大语言模型', category: 'technology', image: '/images/topic-model.png', description: '模型能力与下一步进展', keywords: 'llm 模型 上下文 推理', icon: Cpu },
  { name: '开源生态', category: 'technology', image: '/images/topic-open.png', description: '开放协作，让想法生长', keywords: 'open source github 社区', icon: FileText },
  { name: 'AI 安全', category: 'technology', image: '/images/topic-security.png', description: '关注可信与安全的边界', keywords: 'security 安全 评估 对齐', icon: ScanEye },
  { name: 'AI 产品', category: 'applications', description: '新产品 · 应用实践', keywords: 'product 应用 创业', icon: LayoutGrid },
  { name: '多模态', category: 'applications', description: '图像 · 音频 · 视频', keywords: 'multimodal 图像 音频 视频', icon: ScanEye },
  { name: '算力与芯片', category: 'technology', description: '基础设施 · 芯片进展', keywords: 'gpu compute nvidia 硬件 芯片', icon: Cpu },
  { name: '研究论文', category: 'technology', description: '研究发现 · 技术方法', keywords: 'paper arxiv 论文 研究', icon: FileText },
].filter((topic) => TOPICS.includes(topic.name));
const filtered = computed(() => {
  const term = query.value.trim().toLocaleLowerCase();
  return details.filter((topic) => (category.value === 'all' || topic.category === category.value)
    && (!term || `${topic.name} ${topic.description} ${topic.keywords}`.toLocaleLowerCase().includes(term)));
});
const featured = computed(() => filtered.value.filter((topic) => topic.image));
const otherTopics = computed(() => filtered.value.filter((topic) => !topic.image));
const isFiltered = computed(() => !!query.value.trim() || category.value !== 'all');
function toggle(name: string) {
  if (props.disabled) return;
  emit('update:modelValue', props.modelValue.includes(name) ? props.modelValue.filter((topic) => topic !== name) : [...props.modelValue, name]);
}
function clearFilters() { query.value = ''; category.value = 'all'; }
</script>

<template>
  <section id="topic-options" class="topic-discovery" tabindex="-1" aria-labelledby="topic-title" :aria-describedby="error ? 'topic-error' : undefined">
    <div class="discovery-tabs" role="group" aria-label="主题分类">
      <button v-for="filter in filters" :key="filter.id" type="button" :aria-pressed="category === filter.id" @click="category = filter.id">
        <component :is="filter.icon" :size="18" :stroke-width="1.7" aria-hidden="true" />{{ filter.name }}
      </button>
    </div>

    <h2 id="topic-title">关注你喜欢的主题</h2>
    <div class="discovery-search">
      <Search :size="19" :stroke-width="1.7" aria-hidden="true" />
      <label class="sr-only" for="topic-search">搜索推荐主题或相关关键词</label>
      <input id="topic-search" v-model="query" type="search" placeholder="搜索主题或相关关键词" aria-describedby="topic-search-help" @keydown.enter.prevent />
      <button v-if="query" type="button" class="search-clear" aria-label="清除主题搜索" @click="query = ''"><X :size="18" aria-hidden="true" /></button>
    </div>
    <p id="topic-search-help" class="search-help meta">探索 {{ details.length }} 个推荐主题，例如 Agent、开源或芯片。</p>

    <div v-if="isFiltered" class="filter-summary"><p class="meta" aria-live="polite">找到 {{ filtered.length }} 个主题</p><button type="button" class="discovery-link" @click="clearFilters">清除筛选</button></div>
    <div v-if="featured.length" class="topic-posters" role="group" aria-label="精选关注主题">
      <button v-for="topic in featured" :key="topic.name" type="button" class="topic-poster" :class="{ 'is-selected': modelValue.includes(topic.name) }" :aria-label="`${modelValue.includes(topic.name) ? '取消关注' : '关注'} ${topic.name}`" :aria-pressed="modelValue.includes(topic.name)" :disabled="disabled" @click="toggle(topic.name)">
        <img :src="topic.image" alt="" width="480" height="640" />
        <span class="poster-heading"><strong>{{ topic.name }}</strong><span class="selection-mark"><Check v-if="modelValue.includes(topic.name)" :size="15" :stroke-width="2.4" aria-hidden="true" /><Plus v-else :size="15" aria-hidden="true" /></span></span>
        <span class="poster-description">{{ topic.description }}</span>
      </button>
    </div>

    <div v-if="otherTopics.length" class="more-topics">
      <h3>{{ isFiltered ? '相关主题' : '更多值得关注的方向' }}</h3>
      <div class="topic-directory" role="group" aria-label="更多关注主题">
        <button v-for="topic in otherTopics" :key="topic.name" type="button" class="directory-card" :class="{ 'is-selected': modelValue.includes(topic.name) }" :aria-label="`${modelValue.includes(topic.name) ? '取消关注' : '关注'} ${topic.name}`" :aria-pressed="modelValue.includes(topic.name)" :disabled="disabled" @click="toggle(topic.name)">
          <span class="directory-heading"><strong>{{ topic.name }}</strong><Check v-if="modelValue.includes(topic.name)" :size="16" aria-hidden="true" /><Plus v-else :size="16" aria-hidden="true" /></span>
          <span class="directory-detail"><span class="directory-icon"><component :is="topic.icon" :size="19" :stroke-width="1.7" aria-hidden="true" /></span><span>{{ topic.description }}</span></span>
        </button>
      </div>
    </div>
    <EmptyState v-if="!filtered.length" class="topic-empty" title="没有匹配的主题" description="试试其他关键词，或清除筛选浏览全部主题。你的已选主题会保留。"><button type="button" class="button" @click="clearFilters">清除筛选</button></EmptyState>

    <div class="selected-topics">
      <div class="selected-heading"><h3>已选主题 <span aria-live="polite">{{ modelValue.length }}</span></h3><span class="meta">保存后，下次生成生效</span></div>
      <ul v-if="modelValue.length" class="selected-list"><li v-for="topic in modelValue" :key="topic"><button type="button" :disabled="disabled" :aria-label="`移除已选主题 ${topic}`" @click="toggle(topic)"><Check :size="14" aria-hidden="true" /><span>{{ topic }}</span><X :size="14" aria-hidden="true" /></button></li></ul>
      <p v-else class="meta no-topics">还没有选择主题。你也可以在下方只用关键词定义关注方向。</p>
      <p v-if="error" id="topic-error" class="user-field-error" role="alert">{{ error }}</p>
    </div>
  </section>
</template>

<style scoped>
.topic-discovery { min-width: 0; padding: 0; background: var(--color-surface); border: 0; }
.discovery-tabs { display: flex; gap: var(--space-8); max-width: 100%; overflow-x: auto; border-bottom: 1px solid var(--color-border); margin-bottom: var(--space-8); }
.discovery-tabs button { display: inline-flex; align-items: center; flex-shrink: 0; gap: var(--space-2); min-height: 48px; padding: var(--space-3) 0; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--color-text-muted); font-size: var(--font-size-ui); white-space: nowrap; }
.discovery-tabs button[aria-pressed="true"] { color: var(--color-primary); border-bottom-color: var(--color-accent); font-weight: 600; }
.discovery-tabs button:hover { color: var(--color-primary); }
.topic-discovery h2 { margin: 0 0 var(--space-4); font-size: 20px; font-weight: 600; }
.discovery-search { display: flex; align-items: center; gap: var(--space-3); height: 48px; padding-left: var(--space-4); border: 1px solid var(--color-primary); border-radius: var(--radius-control); color: var(--color-text-muted); }
.discovery-search:focus-within { outline: 2px solid var(--color-primary); outline-offset: 2px; border-color: var(--color-accent); }
.discovery-search > svg { flex-shrink: 0; }
.discovery-search input { min-width: 0; width: 100%; border: 0; background: transparent; outline: none; height: 100%; color: var(--color-text); padding-right: var(--space-3); font-size: var(--font-size-ui); }
.discovery-search input::-webkit-search-cancel-button { display: none; }
.discovery-search input::placeholder { color: var(--color-text-muted); opacity: 1; }
.search-clear { display: grid; place-items: center; flex-shrink: 0; width: 44px; height: 44px; background: none; color: var(--color-text-muted); border: 0; border-radius: var(--radius-control); }
.search-clear:hover { background: var(--color-surface-muted); }
.search-help { margin: var(--space-2) 0 var(--space-8); }
.filter-summary { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); margin: calc(-1 * var(--space-4)) 0 var(--space-4); }
.filter-summary p { margin: 0; }
.discovery-link { min-height: 44px; padding: 0; border: 0; background: none; color: var(--color-primary); font-size: var(--font-size-meta); text-decoration: underline; text-underline-offset: 3px; }
.topic-posters { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-5); }
.topic-poster { position: relative; display: flex; flex-direction: column; justify-content: space-between; min-width: 0; height: 232px; overflow: hidden; border: 2px solid transparent; padding: 0; border-radius: var(--radius-control); background: var(--color-surface-muted); color: var(--color-text-inverse); text-align: left; }
.topic-poster img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.topic-poster.is-selected { border-color: var(--color-accent); }
.topic-poster:hover { border-color: var(--color-primary); }
.poster-heading { position: relative; display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-3); }
.poster-heading strong { min-width: 0; padding: var(--space-1) var(--space-2); border-radius: var(--radius-sm); background: color-mix(in srgb, var(--color-text) 88%, transparent); font-size: var(--font-size-ui); font-weight: 600; }
.selection-mark { display: grid; place-items: center; width: 24px; height: 24px; flex: 0 0 24px; border: 1px solid var(--color-surface); border-radius: 50%; background: var(--color-surface); color: var(--color-primary); }
.is-selected .selection-mark { background: var(--color-primary); color: var(--color-text-inverse); }
.poster-description { position: relative; align-self: flex-start; max-width: calc(100% - 24px); margin: 0 var(--space-3) var(--space-3); padding: var(--space-1) var(--space-2); border-radius: var(--radius-sm); background: color-mix(in srgb, var(--color-text) 88%, transparent); font-size: var(--font-size-xs); line-height: 1.5; }
.more-topics { margin-top: var(--space-8); }
.more-topics h3 { margin-bottom: var(--space-4); font-size: var(--font-size-section); font-weight: 600; }
.topic-directory { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-5); }
.directory-card { display: flex; flex-direction: column; justify-content: space-between; gap: var(--space-6); min-width: 0; min-height: 128px; padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-text); text-align: left; }
.directory-card:hover { border-color: var(--color-primary); background: var(--color-surface-muted); }
.directory-card.is-selected { border-color: var(--color-primary); background: var(--color-primary-soft); }
.directory-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); font-size: var(--font-size-ui); }
.directory-heading strong { font-weight: 500; }
.directory-heading svg { color: var(--color-primary); }
.directory-detail { display: flex; align-items: center; gap: var(--space-2); color: var(--color-text-muted); font-size: var(--font-size-xs); line-height: 1.5; }
.directory-icon { display: grid; place-items: center; width: 32px; height: 32px; flex: 0 0 32px; border-radius: var(--radius-sm); background: var(--color-primary-soft); color: var(--color-primary); }
.topic-empty { margin-block: var(--space-6); }
.selected-topics { padding-top: var(--space-6); margin-top: var(--space-8); border-top: 1px solid var(--color-border); }
.selected-heading { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-3); }
.selected-heading h3 { display: flex; align-items: center; gap: var(--space-2); font-size: var(--font-size-ui); margin: 0; }
.selected-heading h3 > span { min-width: 24px; padding-inline: var(--space-1); background: var(--color-primary-soft); color: var(--color-primary); border-radius: var(--radius-sm); text-align: center; }
.selected-list { display: flex; flex-wrap: wrap; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }
.selected-list li { min-width: 0; max-width: 100%; }
.selected-list button { display: inline-flex; align-items: center; gap: var(--space-2); min-height: 44px; padding: var(--space-2) var(--space-3); border: 1px solid var(--color-primary-border); border-radius: var(--radius-control); color: var(--color-primary); background: var(--color-primary-soft); font-size: var(--font-size-meta); }
.selected-list button span { overflow-wrap: anywhere; }
.selected-list button:hover { border-color: var(--color-primary); }
.topic-poster:disabled, .directory-card:disabled, .selected-list button:disabled { cursor: wait; }
.no-topics { margin: 0; }
@media (max-width: 1023px) {
  .topic-posters, .topic-directory { gap: var(--space-3); }
  .topic-poster { height: 212px; }
  .directory-card { padding: var(--space-3); }
  .directory-detail { align-items: flex-start; flex-direction: column; }
}
@media (max-width: 767px) {
  .discovery-tabs { gap: var(--space-5); margin-bottom: var(--space-6); }
  .discovery-tabs button { font-size: var(--font-size-meta); }
  .topic-discovery h2 { font-size: 18px; }
  .discovery-search { gap: var(--space-2); padding-left: var(--space-3); }
  .discovery-search input { font-size: 16px; }
  .topic-posters, .topic-directory { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .topic-poster { height: 192px; }
  .poster-heading { padding: var(--space-2); gap: var(--space-1); }
  .poster-heading strong { font-size: var(--font-size-meta); }
  .poster-description { max-width: calc(100% - 16px); margin: 0 var(--space-2) var(--space-2); }
  .selection-mark { width: 20px; height: 20px; flex-basis: 20px; }
  .directory-card { min-height: 132px; }
  .directory-detail { flex-direction: row; flex-wrap: wrap; }
  .selected-heading { align-items: flex-start; flex-direction: column; }
}
@media (max-width: 359px) {
  .topic-poster { height: 172px; }
  .poster-heading { align-items: flex-start; }
  .poster-description { font-size: 11px; }
}
</style>
