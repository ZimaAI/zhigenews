<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ArrowRight, Check, Save } from 'lucide-vue-next';
import { api, ApiError, type Preferences } from '@zhigenews/api-client';
import EmptyState from '@ui/EmptyState.vue';
import Modal from '@ui/Modal.vue';
import PreferenceEditor from './PreferenceEditor.vue';
import UnsavedDialog from './UnsavedDialog.vue';
import LoadingState from './LoadingState.vue';
import { sessionState } from '../state';
import { useRequestState } from '../useRequestState';
const props = defineProps<{ onboarding?: boolean }>();
const router = useRouter();
const form = ref<Preferences | null>(null), original = ref('');
const editor = ref<InstanceType<typeof PreferenceEditor>>();
const loading = ref(true), busy = ref(false), success = ref(''), invalid = ref(''), conflict = ref(false), discard = ref(false);
const { error, remaining, fail, clear } = useRequestState();
const dirty = computed(() => !!form.value && (JSON.stringify(form.value) !== original.value || !!editor.value?.hasPendingKeywords));
const controller = new AbortController();
onBeforeUnmount(() => controller.abort());
watch(form, () => { success.value = ''; if (form.value?.topics.length || form.value?.keywords.length) invalid.value = ''; }, { deep: true });
async function load() {
  if (remaining.value) return;
  loading.value = true; clear(); discard.value = false;
  try {
    form.value = await api<Preferences>('getPreferences', { signal: controller.signal });
    original.value = JSON.stringify(form.value); conflict.value = false;
  } catch (exception) { if (!controller.signal.aborted) fail(exception); }
  finally { loading.value = false; }
}
async function save() {
  if (busy.value || remaining.value || !form.value) return;
  invalid.value = ''; clear(); success.value = '';
  if (!editor.value?.commitKeywords()) return;
  await nextTick();
  if (!form.value.topics.length && !form.value.keywords.length) {
    invalid.value = '请选择至少一个话题，或添加关键词。'; document.getElementById('topic-options')?.focus(); return;
  }
  busy.value = true;
  try {
    form.value = await api<Preferences>('savePreferences', { body: form.value });
    original.value = JSON.stringify(form.value); conflict.value = false;
    if (sessionState.session) sessionState.session.onboardingCompleted = true;
    await nextTick(); success.value = '已保存';
    if (props.onboarding) await router.replace('/today');
  } catch (exception) {
    fail(exception);
    conflict.value = exception instanceof ApiError && exception.code === 'VERSION_CONFLICT';
  } finally { busy.value = false; }
}
onMounted(load);
</script>
<template>
  <LoadingState v-if="loading" />
  <EmptyState v-else-if="!form" error title="无法读取订阅偏好" :description="error"><button class="button" :disabled="remaining > 0" @click="load">{{ remaining ? `${remaining} 秒后可重试` : '重新加载' }}</button></EmptyState>
  <form v-else class="preferences-form" aria-label="兴趣订阅" @submit.prevent="save">
    <div v-if="error" class="alert alert--danger" role="alert"><span>{{ error }}<template v-if="conflict"> 当前编辑已保留；可重新载入最新设置后继续修改。</template></span><button v-if="conflict" type="button" class="button" @click="discard = true">重新加载</button></div>
    <PreferenceEditor ref="editor" v-model="form" :id-prefix="onboarding ? 'onboarding' : 'preferences'" :error="invalid" :disabled="busy" />
    <div class="form-actions"><span class="save-status meta" :class="{ 'save-status--success': !!success && !dirty }" role="status"><Check v-if="success && !dirty" :size="14" aria-hidden="true" />{{ dirty ? '未保存' : success }}</span><button class="button button--primary" type="submit" :disabled="busy || remaining > 0 || (!onboarding && !dirty)"><Save v-if="!onboarding" :size="16" aria-hidden="true" />{{ busy ? '正在保存…' : remaining ? `${remaining} 秒后可重试` : onboarding ? '开始阅读' : '保存' }}<ArrowRight v-if="onboarding" :size="16" aria-hidden="true" /></button></div>
    <UnsavedDialog :dirty="dirty" />
    <Modal :open="discard" title="重新加载最新设置" @close="discard = false"><p>重新加载会丢弃当前未保存的修改。</p><template #footer><button class="button" type="button" @click="discard = false">继续编辑</button><button class="button button--primary" type="button" @click="load">丢弃修改并加载</button></template></Modal>
  </form>
</template>
<style scoped>.preferences-form{min-width:0}.preferences-form .form-actions{margin-top:24px;padding-top:24px;border-top:1px solid var(--color-border)}.save-status{min-height:20px}</style>
