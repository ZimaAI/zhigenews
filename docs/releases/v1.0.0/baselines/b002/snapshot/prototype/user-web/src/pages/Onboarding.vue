<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ArrowRight } from 'lucide-vue-next';
import { api, state } from '@shared/mock';
import type { Preferences } from '@shared/types';
import PreferenceEditor from '../components/PreferenceEditor.vue';
import UnsavedDialog from '../components/UnsavedDialog.vue';

const router = useRouter();
const form = ref<Preferences>(JSON.parse(JSON.stringify(state.preferences)));
const initial = JSON.stringify(form.value);
const editor = ref<InstanceType<typeof PreferenceEditor>>();
const completed = ref(false), busy = ref(false), error = ref(''), invalid = ref('');
const dirty = computed(() => !completed.value && (JSON.stringify(form.value) !== initial || !!editor.value?.hasPendingKeywords));
watch(form, () => { if (form.value.topics.length || form.value.keywords.length) invalid.value = ''; }, { deep: true });
async function finish() {
  if (busy.value) return;
  error.value = ''; invalid.value = '';
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
    completed.value = true;
    await router.replace('/today');
  } catch (exception) { error.value = (exception as Error).message; }
  finally { busy.value = false; }
}
</script>

<template>
  <div class="user-form onboarding-page">
    <header class="page-header"><div><h1>定制你的简报</h1><p>选择话题，或添加关键词。</p></div></header>
    <form @submit.prevent="finish">
      <p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p>
      <PreferenceEditor ref="editor" v-model="form" id-prefix="onboarding" :error="invalid" :disabled="busy" />
      <div class="form-actions"><button class="button button--primary" type="submit" :disabled="busy">{{ busy ? '正在保存…' : '开始阅读' }}<ArrowRight :size="16" aria-hidden="true" /></button></div>
    </form>
    <UnsavedDialog :dirty="dirty" />
  </div>
</template>

<style scoped>
.onboarding-page { max-width: 640px; }
.onboarding-page > .page-header { margin-bottom: 32px; }
.onboarding-page .form-actions { justify-content: flex-end; border-top: 1px solid var(--color-border); padding-top: 24px; }
</style>
