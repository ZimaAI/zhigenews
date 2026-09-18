<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { api, state } from '@shared/mock';
import type { Preferences } from '@shared/types';
import PreferenceEditor from '../components/PreferenceEditor.vue';
import UnsavedDialog from '../components/UnsavedDialog.vue';

const form = ref<Preferences>(JSON.parse(JSON.stringify(state.preferences)));
const original = ref(JSON.stringify(form.value));
const editor = ref<InstanceType<typeof PreferenceEditor>>();
const dirty = computed(() => JSON.stringify(form.value) !== original.value || !!editor.value?.hasPendingKeywords);
const busy = ref(false), error = ref(''), success = ref(''), invalid = ref('');
watch(form, () => {
  success.value = '';
  if (form.value.topics.length || form.value.keywords.length) invalid.value = '';
}, { deep: true });
async function save() {
  if (busy.value) return;
  invalid.value = ''; error.value = ''; success.value = '';
  if (!editor.value?.commitKeywords()) return;
  await nextTick();
  if (!form.value.topics.length && !form.value.keywords.length) {
    invalid.value = '请选择至少一个话题，或添加关键词。';
    document.getElementById('topic-options')?.focus();
    return;
  }
  busy.value = true;
  try {
    await api.savePreferences(JSON.parse(JSON.stringify(form.value)));
    form.value = JSON.parse(JSON.stringify(state.preferences));
    original.value = JSON.stringify(form.value);
    await nextTick();
    success.value = '已保存';
  } catch (exception) { error.value = (exception as Error).message; }
  finally { busy.value = false; }
}
</script>

<template>
  <form class="preferences-form" aria-label="兴趣订阅" @submit.prevent="save">
    <p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p>
    <PreferenceEditor ref="editor" v-model="form" :error="invalid" :disabled="busy" />
    <div class="form-actions"><span class="save-status meta" role="status">{{ dirty ? '未保存' : success }}</span><button class="button button--primary" type="submit" :disabled="busy || !dirty">{{ busy ? '正在保存…' : '保存' }}</button></div>
    <UnsavedDialog :dirty="dirty" />
  </form>
</template>

<style scoped>
.preferences-form { min-width: 0; }
.preferences-form .form-actions { margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--color-border); }
.save-status { min-height: 20px; }
</style>
