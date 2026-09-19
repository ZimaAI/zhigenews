<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { Check, Clock3, Save } from 'lucide-vue-next';
import { api, type DeliverySettings } from '@zhigenews/api-client';
import EmptyState from '@ui/EmptyState.vue';
import UnsavedDialog from '../components/UnsavedDialog.vue';
import LoadingState from '../components/LoadingState.vue';
import { useRequestState } from '../useRequestState';
const form = ref<DeliverySettings | null>(null), original = ref('');
const dirty = computed(() => !!form.value && form.value.time !== original.value);
const loading = ref(true), busy = ref(false), success = ref('');
const { error, remaining, fail, clear } = useRequestState();
const controller = new AbortController();
onBeforeUnmount(() => controller.abort());
watch(() => form.value?.time, () => { success.value = ''; });
async function load() {
  if (remaining.value) return;
  loading.value = true; clear();
  try { form.value = await api<DeliverySettings>('getDeliverySettings', { signal: controller.signal }); original.value = form.value.time; }
  catch (exception) { if (!controller.signal.aborted) fail(exception); }
  finally { loading.value = false; }
}
async function save() {
  if (busy.value || remaining.value || !form.value) return;
  busy.value = true; clear(); success.value = '';
  try { form.value = await api<DeliverySettings>('saveDeliverySettings', { body: { time: form.value.time } }); original.value = form.value.time; success.value = '已保存'; }
  catch (exception) { fail(exception); } finally { busy.value = false; }
}
onMounted(load);
</script>
<template>
  <LoadingState v-if="loading" />
  <EmptyState v-else-if="!form" error title="无法读取推送时间" :description="error"><button class="button" :disabled="remaining > 0" @click="load">{{ remaining ? `${remaining} 秒后可重试` : '重新加载' }}</button></EmptyState>
  <form v-else class="delivery-form" aria-label="推送时间" @submit.prevent="save">
    <p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p>
    <div class="field schedule-field"><label for="delivery-time"><Clock3 :size="16" :stroke-width="1.8" aria-hidden="true" />每天自动推送时间</label><input id="delivery-time" v-model="form.time" class="field-control" type="time" required :disabled="busy" /><p class="meta">按北京时间（Asia/Shanghai）每日站内推送。</p></div>
    <div class="form-actions"><span class="save-status meta" :class="{ 'save-status--success': !!success }" role="status"><Check v-if="success" :size="14" aria-hidden="true" />{{ success || (dirty ? '未保存' : '') }}</span><button class="button button--primary" type="submit" :disabled="busy || !dirty || remaining > 0"><Save :size="16" :stroke-width="1.8" aria-hidden="true" />{{ busy ? '正在保存…' : remaining ? `${remaining} 秒后可重试` : '保存' }}</button></div>
    <UnsavedDialog :dirty="dirty" />
  </form>
</template>
<style scoped>
.delivery-form { min-width: 0; }
.schedule-field { max-width: 240px; }
.schedule-field label { display: inline-flex; align-items: center; gap: 8px; }
.schedule-field label svg { color: var(--color-primary); }
.delivery-form .form-actions { margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--color-border); }
.save-status { min-height: 20px; }
</style>
