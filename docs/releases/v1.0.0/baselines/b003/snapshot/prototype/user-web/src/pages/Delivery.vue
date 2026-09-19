<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Check, Clock3, Save } from 'lucide-vue-next';
import { api, state } from '@shared/mock';
import type { DeliverySettings } from '@shared/types';
import UnsavedDialog from '../components/UnsavedDialog.vue';

const form = ref<DeliverySettings>({ time: state.delivery.time });
const original = ref(form.value.time);
const dirty = computed(() => form.value.time !== original.value);
const busy = ref(false), error = ref(''), success = ref('');
watch(() => form.value.time, () => { success.value = ''; error.value = ''; });
async function save() {
  if (busy.value) return;
  busy.value = true; error.value = ''; success.value = '';
  try {
    await api.saveDelivery({ time: form.value.time });
    form.value.time = state.delivery.time;
    original.value = form.value.time;
    success.value = '已保存';
  } catch (exception) { error.value = (exception as Error).message; }
  finally { busy.value = false; }
}
</script>

<template>
  <form class="delivery-form" aria-label="推送时间" @submit.prevent="save">
    <p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p>
    <div class="field schedule-field"><label for="delivery-time"><Clock3 :size="16" :stroke-width="1.8" aria-hidden="true" />每天自动推送时间</label><input id="delivery-time" v-model="form.time" class="field-control" type="time" required :disabled="busy" /></div>
    <div class="form-actions"><span class="save-status meta" :class="{ 'save-status--success': !!success }" role="status"><Check v-if="success" :size="14" aria-hidden="true" />{{ success || (dirty ? '未保存' : '') }}</span><button class="button button--primary" type="submit" :disabled="busy || !dirty"><Save :size="16" :stroke-width="1.8" aria-hidden="true" />{{ busy ? '正在保存…' : '保存' }}</button></div>
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
