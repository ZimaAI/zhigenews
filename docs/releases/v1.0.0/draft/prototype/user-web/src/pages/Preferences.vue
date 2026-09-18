<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { Check, Plus, Save, Trash2, Brain, ArrowUpRight } from 'lucide-vue-next';
import { api, state, TOPICS } from '@shared/mock';
import type { Preferences } from '@shared/types';
import Modal from '@shared/Modal.vue';
import EmptyState from '@shared/EmptyState.vue';
import KeywordInput from '../components/KeywordInput.vue';
import UnsavedDialog from '../components/UnsavedDialog.vue';
const form = reactive<Preferences>(JSON.parse(JSON.stringify(state.preferences)));
const original = ref(JSON.stringify(form));
const dirty = computed(() => JSON.stringify(form) !== original.value);
const busy = ref(false), error = ref(''), success = ref('');
const invalid = ref('');
const deleteId = ref(''), deleteBusy = ref(false), deleteError = ref('');
const memory = computed(() => state.memories.find((m) => m.id === deleteId.value));
watch(form, () => { success.value = ''; if (form.topics.length || form.keywords.length) invalid.value = ''; });
function toggleTopic(topic: string) { form.topics = form.topics.includes(topic) ? form.topics.filter((t) => t !== topic) : [...form.topics, topic]; }
async function save() {
  if (busy.value) return;
  invalid.value = ''; error.value = ''; success.value = '';
  if (!form.topics.length && !form.keywords.length) { invalid.value = '请至少选择一个主题，或添加一个包含关键词。'; document.getElementById('topic-options')?.focus(); return; }
  if (form.keywordMode === 'required' && !form.keywords.length) { error.value = '选择“必须包含”时，请至少添加一个包含关键词。'; document.getElementById('include-keywords')?.focus(); return; }
  if (form.keywords.some((v) => form.excludedKeywords.includes(v))) { error.value = '同一个关键词不能同时包含和排除，请检查关键词设置。'; return; }
  if (!form.sourceTypes.length) { error.value = '请至少选择一种来源类型。'; return; }
  busy.value = true;
  try { await api.savePreferences(JSON.parse(JSON.stringify(form))); Object.assign(form, JSON.parse(JSON.stringify(state.preferences))); original.value = JSON.stringify(form); success.value = '订阅已保存，下次生成将使用新偏好。现有简报保持原来的内容与快照。'; } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; }
}
async function removeMemory() { if (deleteBusy.value) return; deleteBusy.value = true; deleteError.value = ''; try { await api.deleteMemory(deleteId.value); deleteId.value = ''; } catch (e) { deleteError.value = (e as Error).message; } finally { deleteBusy.value = false; } }
</script>
<template>
  <div class="user-form">
    <header class="page-header"><div><p class="eyebrow">MAKE IT YOURS</p><h1>兴趣订阅</h1><p class="muted">决定你关心什么，也决定什么可以略过。</p></div><span class="meta">已保存版本 {{ state.preferences.version }}</span></header>
    <form @submit.prevent="save">
      <div v-if="error" class="alert alert--danger" role="alert">{{ error }} 修改保留，可再次保存重试。</div>
      <div v-if="success" class="alert alert--success" role="status">{{ success }}</div>
      <section class="card"><h2>你的关注方向</h2><p class="section-note">作为筛选背景，不是你的实名身份。越具体，推荐理由越容易解释。</p><div class="field"><label for="interest-role">角色或关注背景</label><textarea id="interest-role" v-model="form.role" class="field-control" maxlength="500" rows="3" placeholder="例如：正在构建 AI 应用的 Python 开发者，关注 Agent 工程化和开源模型。"></textarea><span class="meta">{{ form.role.length }} / 500</span></div></section>
      <section class="card"><h2>关注主题</h2><p class="section-note">主题和包含关键词至少设置一项。也可以不选主题，只通过关键词定义关注方向。</p><div id="topic-options" tabindex="-1" class="user-topic-grid" role="group" aria-label="关注主题" :aria-describedby="invalid ? 'topic-error' : undefined"><button v-for="topic in TOPICS" :key="topic" type="button" class="chip" :class="{ 'chip--active': form.topics.includes(topic) }" :aria-pressed="form.topics.includes(topic)" @click="toggleTopic(topic)"><Check v-if="form.topics.includes(topic)" :size="14" aria-hidden="true" /><Plus v-else :size="14" aria-hidden="true" />{{ topic }}</button></div><p v-if="invalid" id="topic-error" class="user-field-error" role="alert">{{ invalid }}</p></section>
      <section class="card"><h2>关键词与排除项</h2><p class="section-note">关键词不支持复杂布尔表达式。排除规则优先于包含规则。</p><div class="stack"><KeywordInput v-model="form.keywords" id="include-keywords" label="包含关键词" description="希望更多看到的技术、公司或产品。" /><fieldset><legend>包含关键词的匹配方式</legend><label class="check-label"><input v-model="form.keywordMode" type="radio" value="prefer" />优先推荐相关内容，允许主题内其他重要消息</label><label class="check-label"><input v-model="form.keywordMode" type="radio" value="required" />必须包含至少一个关键词</label></fieldset><KeywordInput v-model="form.excludedKeywords" id="exclude-keywords" label="排除关键词" description="命中这些词的内容不进入本期简报。" /></div></section>
      <section class="card"><h2>简报偏好</h2><p class="section-note">控制来源、阅读篇幅与信息范围。</p><div class="stack"><fieldset><legend>使用的来源类型</legend><div class="source-checks"><label class="check-label"><input v-model="form.sourceTypes" type="checkbox" value="newsnow" />NewsNow 热榜</label><label class="check-label"><input v-model="form.sourceTypes" type="checkbox" value="rss" />RSS 订阅</label><label class="check-label"><input v-model="form.sourceTypes" type="checkbox" value="search" />Agent 网络搜索</label></div></fieldset><div class="form-grid"><div class="field"><label for="window-hours">新闻时间范围</label><select id="window-hours" v-model.number="form.windowHours" class="field-control"><option :value="24">最近 24 小时</option><option :value="48">最近 48 小时</option><option :value="72">最近 3 天</option><option :value="168">最近 7 天</option></select></div><div class="field"><label for="max-items">每期最多条数</label><input id="max-items" v-model.number="form.maxItems" type="number" min="1" max="30" required class="field-control" /><span class="meta">1–30 条；不足时不凑数。</span></div><div class="field"><label for="language">简报语言</label><select id="language" v-model="form.language" class="field-control"><option value="简体中文">简体中文</option><option value="English">English</option></select></div><div class="field"><label for="depth">摘要深度</label><select id="depth" v-model="form.depth" class="field-control"><option>精简</option><option>标准</option><option>深入</option></select></div></div></div></section>
      <div class="form-actions"><p class="meta">{{ dirty ? '有未保存的修改' : '所有修改已保存' }} · 保存后下次生成生效</p><button class="button button--primary" type="submit" :disabled="busy || !dirty"><Save :size="16" aria-hidden="true" />{{ busy ? '正在保存…' : '保存订阅' }}</button></div>
    </form>
    <section class="card memory-section"><div class="memory-heading"><Brain :size="20" aria-hidden="true" /><h2>长期记忆</h2></div><p class="section-note">可跨简报复用的阅读偏好。清理后，后续生成不再使用该条记忆；已生成内容不变。</p><EmptyState v-if="!state.memories.length" title="没有已保存的记忆" description="你的显式订阅仍然有效。这里仅展示可独立清理的长期记忆。" /><ul v-else class="user-plain-list memory-list"><li v-for="item in state.memories" :key="item.id"><div><p>{{ item.text }}</p><span class="meta">来源：{{ item.source }} · {{ item.updatedAt }}</span></div><button class="button button--ghost" :aria-label="`清理记忆：${item.text}`" @click="deleteId = item.id; deleteError = ''"><Trash2 :size="16" aria-hidden="true" /><span>清理</span></button></li></ul></section>
    <p class="meta preference-link">推送时间、时区和收件渠道在 <RouterLink to="/delivery">推送设置<ArrowUpRight :size="13" aria-hidden="true" /></RouterLink> 中管理。</p>
    <Modal :open="!!deleteId" title="清理这条长期记忆？" @close="!deleteBusy && (deleteId = '')"><p>{{ memory?.text }}</p><p class="meta">清理不能撤销。你仍可在兴趣订阅中重新明确表达这个偏好。</p><p v-if="deleteError" class="alert alert--danger" role="alert">{{ deleteError }} 原记忆已保留，可以重试。</p><template #footer><button class="button" :disabled="deleteBusy" @click="deleteId = ''">保留记忆</button><button class="button button--primary" :disabled="deleteBusy" @click="removeMemory">{{ deleteBusy ? '正在清理…' : '清理记忆' }}</button></template></Modal>
    <UnsavedDialog :dirty="dirty" />
  </div>
</template>
<style scoped>
.source-checks { display: flex; flex-wrap: wrap; gap: 12px 24px; }
.memory-section { margin-top: 24px; }
.memory-heading { display: flex; align-items: center; gap: 8px; }
.memory-heading svg { color: var(--color-primary); }
.memory-heading h2 { margin: 0; }
.memory-section .section-note { margin-top: 8px; }
.memory-list li { display: flex; align-items: flex-start; gap: 16px; padding-block: 16px; border-top: 1px solid var(--color-border); }
.memory-list li > div { flex: 1; min-width: 0; }
.memory-list p { margin: 0 0 8px; font-size: 14px; }
.memory-list .button { flex-shrink: 0; }
.preference-link { margin-block: 24px; }
.preference-link a svg { vertical-align: middle; margin-left: 4px; }
form > .alert { margin-bottom: 24px; }
</style>
