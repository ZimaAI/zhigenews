<script setup lang="ts">
import { computed, reactive, ref, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { Check, Plus, ArrowLeft, ArrowRight, Sparkles } from 'lucide-vue-next';
import { api, state, TOPICS } from '@shared/mock';
import type { Preferences } from '@shared/types';
import KeywordInput from '../components/KeywordInput.vue';
import UnsavedDialog from '../components/UnsavedDialog.vue';
const router = useRouter();
const step = ref(1), busy = ref(false), error = ref(''), completed = ref(false);
const draftKey = 'zhigenews-onboarding-draft-v1';
let savedDraft: any;
try { savedDraft = JSON.parse(sessionStorage.getItem(draftKey) || 'null'); } catch { savedDraft = null; }
const form = reactive<Preferences>(savedDraft?.preferences || JSON.parse(JSON.stringify(state.preferences)));
const channel = reactive({ enabled: savedDraft?.emailEnabled ?? false, email: savedDraft?.email || '', time: savedDraft?.time || '08:00', timezone: savedDraft?.timezone || 'Asia/Shanghai' });
const initial = JSON.stringify({ form, channel });
const dirty = computed(() => !completed.value && JSON.stringify({ form, channel }) !== initial);
const restored = ref(!!savedDraft);
watch([form, channel], () => { sessionStorage.setItem(draftKey, JSON.stringify({ preferences: form, emailEnabled: channel.enabled, email: channel.email, time: channel.time, timezone: channel.timezone })); error.value = ''; }, { deep: true });
function toggle(topic: string) { form.topics = form.topics.includes(topic) ? form.topics.filter((t) => t !== topic) : [...form.topics, topic]; }
function next() { error.value = ''; step.value++; }
async function finish() {
  if (busy.value) return;
  error.value = '';
  if (!form.topics.length && !form.keywords.length) {
    step.value = 2;
    error.value = '请至少选择一个主题，或添加一个包含关键词，再保存订阅。';
    await nextTick();
    document.getElementById('onboarding-keywords')?.focus();
    return;
  }
  busy.value = true;
  try { await api.savePreferences(JSON.parse(JSON.stringify(form))); await api.saveDelivery({ ...state.delivery, emailEnabled: channel.enabled, email: channel.enabled ? channel.email : state.delivery.email, verified: channel.email === state.delivery.email && state.delivery.verified, time: channel.time, timezone: channel.timezone, dailyEnabled: true }); completed.value = true; sessionStorage.removeItem(draftKey); await router.push('/today'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; }
}
</script>
<template>
  <div class="user-form onboarding-page">
    <header class="page-header"><div><p class="eyebrow">A BRIEF THAT KNOWS YOUR INTERESTS</p><h1>从你的关注开始</h1><p class="muted">三个简单步骤，准备好第一份个人简报。</p></div></header>
    <ol class="steps" aria-label="首次配置进度"><li v-for="(label, index) in ['关注背景', '兴趣主题', '推送计划']" :key="label" :class="{ active: step === index + 1, complete: step > index + 1 }" :aria-current="step === index + 1 ? 'step' : undefined"><span class="step-number"><Check v-if="step > index + 1" :size="14" aria-hidden="true" /><template v-else>{{ index + 1 }}</template></span><span>{{ label }}</span></li></ol>
    <p v-if="restored" class="alert" role="status">已恢复本标签页上次的配置草稿。<button class="button button--ghost" @click="restored = false">知道了</button></p>
    <p v-if="error" class="alert alert--danger" role="alert">{{ error }} 草稿仍保留。</p>
    <form @submit.prevent="step < 3 ? next() : finish()">
      <section v-if="step === 1" class="card"><p class="meta">第 1 步，共 3 步</p><h2>什么信息对你有价值？</h2><p class="section-note">可以用一句话介绍你的工作或关注方向，也可以暂时留空。</p><div class="field"><label for="onboarding-role">角色或关注背景（选填）</label><textarea id="onboarding-role" v-model="form.role" class="field-control" rows="5" maxlength="500" placeholder="例如：我是产品开发者，想了解 AI 应用、Agent 实践和开源工具。"></textarea><span class="meta">{{ form.role.length }} / 500 · 不需要填写真实姓名或单位</span></div></section>
      <section v-if="step === 2" class="card"><p class="meta">第 2 步，共 3 步</p><h2>选择你的阅读方向</h2><p class="section-note">选择主题或添加关键词，至少设置一项；可以只用关键词定义关注方向。</p><div class="user-topic-grid" role="group" aria-label="选择关注主题"><button v-for="topic in TOPICS" :key="topic" type="button" class="chip" :class="{ 'chip--active': form.topics.includes(topic) }" :aria-pressed="form.topics.includes(topic)" @click="toggle(topic)"><Check v-if="form.topics.includes(topic)" :size="14" aria-hidden="true" /><Plus v-else :size="14" aria-hidden="true" />{{ topic }}</button></div><hr class="user-divider" /><KeywordInput v-model="form.keywords" id="onboarding-keywords" label="特别关注的关键词（选填）" description="作为优先推荐线索，不强制每条都命中。" /></section>
      <section v-if="step === 3" class="card"><p class="meta">第 3 步，共 3 步</p><h2>让简报按时来</h2><p class="section-note">默认保存在站内。邮件是可选的，跳过后仍可完整阅读。</p><label class="check-label"><input v-model="channel.enabled" type="checkbox" />同时通过邮件接收简报</label><div v-if="channel.enabled" class="field onboarding-email"><label for="onboarding-email">收件邮箱</label><input id="onboarding-email" v-model="channel.email" class="field-control" type="email" required placeholder="you@example.com" /><span class="meta">保存后需前往推送设置完成模拟验证。本原型不会发送邮件。</span></div><div class="form-grid"><div class="field"><label for="onboarding-time">每日整理时间</label><input id="onboarding-time" v-model="channel.time" class="field-control" type="time" required /></div><div class="field"><label for="onboarding-zone">时区</label><select id="onboarding-zone" v-model="channel.timezone" class="field-control"><option>Asia/Shanghai</option><option>Asia/Tokyo</option><option>America/New_York</option><option>Europe/London</option><option>UTC</option></select></div></div><div class="setup-summary"><Sparkles :size="18" aria-hidden="true" /><p>你的简报将关注 <strong>{{ [...new Set([...form.topics, ...form.keywords])].join('、') || '尚未设置的阅读方向' }}</strong>，每期最多 {{ form.maxItems }} 条，以{{ form.language }}呈现。</p></div></section>
      <div class="form-actions"><button v-if="step > 1" class="button" type="button" :disabled="busy" @click="step--; error = ''"><ArrowLeft :size="16" aria-hidden="true" />上一步</button><RouterLink v-else class="button button--ghost" to="/today">稍后再配置</RouterLink><button class="button button--primary" type="submit" :disabled="busy">{{ busy ? '正在保存…' : step === 3 ? '保存并进入今日简报' : '继续' }}<ArrowRight :size="16" aria-hidden="true" /></button></div>
    </form>
    <p class="meta draft-note">输入会保存在本标签页草稿中；保存完成后才用于模拟生成。</p>
    <UnsavedDialog :dirty="dirty" />
  </div>
</template>
<style scoped>
.steps { display: flex; list-style: none; padding: 0; margin: 32px 0; gap: 16px; }
.steps li { display: flex; align-items: center; gap: 8px; flex: 1; font-size: 14px; color: var(--color-text-muted); }
.steps li:not(:last-child)::after { content: ''; flex: 1; height: 1px; background: var(--color-border); margin-left: 8px; }
.step-number { width: 28px; height: 28px; border: 1px solid var(--color-border-control); border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 12px; }
.steps li.active, .steps li.complete { color: var(--color-primary); }
.steps li.active .step-number, .steps li.complete .step-number { background: var(--color-primary-soft); border-color: var(--color-primary); }
.onboarding-page .card > p:first-child { margin-top: 0; }
.onboarding-page .form-grid { margin-top: 24px; }
.onboarding-email { margin-top: 16px; }
.setup-summary { display: flex; gap: 12px; background: var(--color-surface-muted); border-radius: var(--radius-card); padding: 16px; margin-top: 24px; }
.setup-summary svg { color: var(--color-primary); flex-shrink: 0; margin-top: 4px; }
.setup-summary p { margin: 0; font-size: 14px; color: var(--color-text-secondary); }
.draft-note { text-align: center; }
@media (max-width: 480px) { .steps { gap: 8px; } .steps li { gap: 4px; font-size: 12px; } .steps li:not(:last-child)::after { display: none; } .step-number { width: 24px; height: 24px; } }
</style>
