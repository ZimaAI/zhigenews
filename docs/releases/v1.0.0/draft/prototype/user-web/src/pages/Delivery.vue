<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { Save, Mail, Inbox, Send, Pause, Play, Check, RotateCw, Clock3 } from 'lucide-vue-next';
import { api, state } from '@shared/mock';
import type { DeliverySettings } from '@shared/types';
import Badge from '@shared/Badge.vue';
import EmptyState from '@shared/EmptyState.vue';
import UnsavedDialog from '../components/UnsavedDialog.vue';
const form = reactive<DeliverySettings>(JSON.parse(JSON.stringify(state.delivery)));
const original = ref(JSON.stringify(form));
const dirty = computed(() => JSON.stringify(form) !== original.value);
const busy = ref(''), error = ref(''), success = ref('');
const records = computed(() => state.deliveries.filter((d) => d.userName === state.runs[0]?.userName || state.briefs.some((b) => b.id === d.briefId)));
watch(() => form.email, (value, old) => { if (value !== old) form.verified = value === state.delivery.email && state.delivery.verified; });
function sync() { Object.assign(form, JSON.parse(JSON.stringify(state.delivery))); original.value = JSON.stringify(form); }
async function action(name: string, operation: () => Promise<void>, message: string, refresh = false) { if (busy.value) return; busy.value = name; error.value = ''; success.value = ''; try { await operation(); if (refresh) sync(); success.value = message; } catch (e) { error.value = (e as Error).message; } finally { busy.value = ''; } }
function save() { action('save', () => api.saveDelivery(JSON.parse(JSON.stringify(form))), '推送设置已保存。下一次运行时间已按所选时区更新。', true); }
function toggle() { action('pause', () => api.saveDelivery({ ...state.delivery, dailyEnabled: !state.delivery.dailyEnabled }), state.delivery.dailyEnabled ? '每日推送已暂停。历史简报仍可阅读。' : '每日推送已恢复，将从下一次计划时间运行，不补发遗漏简报。', true); }
function mask(email: string) { return email.replace(/^(.{1,2}).*(@.*)$/, '$1•••$2'); }
</script>
<template>
  <div class="user-form">
    <header class="page-header"><div><p class="eyebrow">A QUIETER ROUTINE</p><h1>推送设置</h1><p class="muted">在适合你的时间，收到一份值得读的简报。</p></div></header>
    <p v-if="error" class="alert alert--danger" role="alert">{{ error }} 已保留设置，可再次执行操作重试。</p>
    <p v-if="success" class="alert alert--success" role="status">{{ success }}</p>
    <form @submit.prevent="save">
      <section class="card"><h2>阅读与接收渠道</h2><p class="section-note">每份简报都会保留在站内。邮件是可选渠道，模拟验证和测试不会发送真实邮件。</p><div class="channel-row"><Inbox :size="21" aria-hidden="true" /><div><strong>站内简报</strong><p class="meta">随时回来阅读，完整保留来源与生成快照。</p></div><span class="channel-enabled"><Check :size="14" aria-hidden="true" />默认启用</span></div><div class="channel-row"><Mail :size="21" aria-hidden="true" /><div><strong>电子邮件</strong><p class="meta">每天最多一份，需先保存并验证收件地址。</p></div><label class="check-label"><input v-model="form.emailEnabled" type="checkbox" /><span>启用</span></label></div><div v-if="form.emailEnabled" class="email-fields"><div class="field"><label for="delivery-email">收件邮箱</label><input id="delivery-email" v-model="form.email" type="email" required class="field-control" placeholder="you@example.com" autocomplete="email" /><span class="meta">仅用于这项订阅。测试发送是独立操作，不会随保存触发。</span></div><div class="email-status"><span :class="form.verified ? 'verified' : 'muted'">{{ form.verified ? '已验证（模拟）' : '尚未验证' }}</span><button type="button" class="button button--ghost" :disabled="!!busy || dirty || form.verified || !form.email" @click="action('verify', () => api.verifyEmail(), '模拟邮箱验证完成，未发送验证邮件。', true)">{{ busy === 'verify' ? '正在验证…' : '模拟完成邮箱验证' }}</button></div><p v-if="dirty" class="meta">请先保存地址，再验证或发送测试。</p></div></section>
      <section class="card"><h2>每日计划</h2><p class="section-note">以所选时区的当地时间运行。夏令时跳过的时间顺延至下一个有效时刻，重复时刻只运行一次。</p><div class="form-grid"><div class="field"><label for="delivery-time">推送时间</label><input id="delivery-time" v-model="form.time" class="field-control" type="time" required /></div><div class="field"><label for="delivery-timezone">时区</label><select id="delivery-timezone" v-model="form.timezone" class="field-control"><option value="Asia/Shanghai">中国标准时间 · Asia/Shanghai</option><option value="Asia/Tokyo">日本标准时间 · Asia/Tokyo</option><option value="America/New_York">纽约 · America/New_York</option><option value="Europe/London">伦敦 · Europe/London</option><option value="UTC">协调世界时 · UTC</option></select></div></div><div class="schedule-preview"><Clock3 :size="18" aria-hidden="true" /><div><strong>{{ state.delivery.dailyEnabled ? '下一次计划（固定演示时钟）' : '每日推送已暂停' }}</strong><p>{{ state.delivery.dailyEnabled ? state.delivery.nextRunAt : '恢复后，将从下一次计划时间继续。' }}</p><span v-if="dirty" class="meta">保存后按新时间重新计算。</span></div></div></section>
      <div class="form-actions"><p class="meta">{{ dirty ? '有未保存的修改' : '设置已保存' }}</p><button class="button button--primary" type="submit" :disabled="!!busy || !dirty"><Save :size="16" aria-hidden="true" />{{ busy === 'save' ? '正在保存…' : '保存设置' }}</button></div>
    </form>
    <section class="card delivery-actions"><h2>测试与暂停</h2><p class="section-note">保存、测试、暂停分别生效，避免误发或重复生成。</p><div class="operation-row"><div><strong>发送一封测试简报</strong><p class="meta">{{ state.delivery.emailEnabled ? `发往 ${mask(state.delivery.email)}` : '请先启用电子邮件' }} · 原型模拟</p><p v-if="!state.delivery.verified" class="meta">启用邮件、保存地址并完成模拟验证后可测试。</p></div><button class="button" :disabled="!!busy || dirty || !state.delivery.emailEnabled || !state.delivery.verified" @click="action('test', () => api.testDelivery(), '模拟测试邮件已提交。未实际发送，不代表送达。')"><Send :size="16" aria-hidden="true" />{{ busy === 'test' ? '正在提交…' : '发送测试' }}</button></div><div class="operation-row"><div><strong>{{ state.delivery.dailyEnabled ? '暂停每日推送' : '恢复每日推送' }}</strong><p class="meta">不删除历史，也不停止手动生成。</p></div><button class="button" :disabled="!!busy || dirty" @click="toggle"><Pause v-if="state.delivery.dailyEnabled" :size="16" aria-hidden="true" /><Play v-else :size="16" aria-hidden="true" />{{ busy === 'pause' ? '正在更新…' : state.delivery.dailyEnabled ? '暂停推送' : '恢复推送' }}</button></div><p v-if="dirty" class="meta">请先保存当前修改，再测试或暂停。</p></section>
    <section class="card delivery-history"><h2>最近投递</h2><p class="section-note">内容生成和邮件投递分别记录，重试会发送原来的同一期。</p><EmptyState v-if="!records.length" title="还没有投递记录" description="启用邮件后，投递尝试会显示在这里。" /><ul v-else class="user-plain-list"><li v-for="record in records.slice(0, 5)" :key="record.id"><div class="delivery-record-head"><RouterLink v-if="record.briefId" :to="`/briefs/${record.briefId}`">{{ state.briefs.find((b) => b.id === record.briefId)?.title || '历史简报' }}</RouterLink><strong v-else>测试邮件（模拟）</strong><Badge :status="record.status" /></div><p class="meta">{{ record.destination }} · {{ record.time }} · 尝试 {{ record.attempts }} 次</p><p v-if="record.error" class="user-field-error">{{ record.error }}</p><button v-if="['failed', 'unknown'].includes(record.status)" class="button button--ghost" :disabled="!!busy" @click="action(`retry-${record.id}`, () => api.retryDelivery(record.id), '已模拟重新提交同一期内容，送达仍待确认。')"><RotateCw :size="14" aria-hidden="true" />{{ busy === `retry-${record.id}` ? '正在重试…' : '重试推送同一期' }}</button></li></ul></section>
    <UnsavedDialog :dirty="dirty" />
  </div>
</template>
<style scoped>
.channel-row { display: flex; align-items: center; gap: 16px; padding: 20px 0; border-top: 1px solid var(--color-border); }
.channel-row > svg { color: var(--color-primary); flex: 0 0 21px; }
.channel-row > div { flex: 1; min-width: 0; }
.channel-row strong, .operation-row strong { font-size: 14px; font-weight: 600; }
.channel-row p, .operation-row p { margin: 4px 0 0; }
.channel-enabled { display: flex; align-items: center; gap: 6px; font-size: 12px; white-space: nowrap; color: var(--color-primary); }
.email-fields { padding: 0 0 4px 36px; }
.email-status { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 8px; font-size: 13px; }
.verified { color: var(--color-success); }
.schedule-preview { display: flex; align-items: flex-start; gap: 12px; margin-top: 24px; padding: 16px; border-radius: 8px; background: var(--color-surface-muted); }
.schedule-preview > svg { color: var(--color-primary); margin-top: 2px; flex-shrink: 0; }
.schedule-preview strong { font-size: 13px; font-weight: 500; }
.schedule-preview p { margin: 4px 0 0; font-size: 14px; overflow-wrap: anywhere; }
.delivery-actions { margin-top: 24px; }
.operation-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding-block: 20px; border-top: 1px solid var(--color-border); }
.operation-row .button { flex-shrink: 0; }
.delivery-history li { border-top: 1px solid var(--color-border); padding-block: 20px; }
.delivery-history li:last-child { padding-bottom: 0; }
.delivery-record-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.delivery-record-head a { font-size: 14px; text-decoration: none; }
.delivery-history li > p { margin: 8px 0; }
@media (max-width: 480px) { .channel-row { flex-wrap: wrap; gap: 12px; } .channel-row > div { flex-basis: calc(100% - 36px); } .channel-row > label, .channel-enabled { margin-left: 33px; } .email-fields { padding-left: 0; } .operation-row { flex-wrap: wrap; } }
</style>
