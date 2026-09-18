<script setup lang="ts">
import { computed, ref } from 'vue';
import type { Preferences } from '@shared/types';
import TopicDiscovery from './TopicDiscovery.vue';
import KeywordInput from './KeywordInput.vue';

const props = defineProps<{ modelValue: Preferences; error?: string; disabled?: boolean; idPrefix?: string }>();
const emit = defineEmits<{ 'update:modelValue': [preferences: Preferences] }>();
const keywords = ref<InstanceType<typeof KeywordInput>>();
const prefix = computed(() => props.idPrefix || 'preferences');
function update(patch: Partial<Preferences>) { emit('update:modelValue', { ...props.modelValue, ...patch }); }
const hasPendingKeywords = computed(() => keywords.value?.pending ?? false);
function commitKeywords() { return keywords.value?.flush() ?? true; }
defineExpose({ commitKeywords, hasPendingKeywords });
</script>

<template>
  <div class="preference-editor">
    <TopicDiscovery :model-value="modelValue.topics" :error="error" :disabled="disabled" @update:model-value="update({ topics: $event })" />
    <div class="field"><label :for="`${prefix}-role`">背景 <span class="optional">选填</span></label><textarea :id="`${prefix}-role`" :value="modelValue.role" class="field-control" maxlength="500" rows="3" :disabled="disabled" placeholder="例如：Python 开发者，关注 Agent 和开源工具" @input="update({ role: ($event.target as HTMLTextAreaElement).value })"></textarea></div>
    <KeywordInput ref="keywords" :id="`${prefix}-keywords`" :model-value="modelValue.keywords" label="关键词" :disabled="disabled" @update:model-value="update({ keywords: $event })" />
  </div>
</template>

<style scoped>
.preference-editor { display: flex; flex-direction: column; gap: 28px; min-width: 0; }
.optional { margin-left: 4px; color: var(--color-text-muted); font-size: 12px; font-weight: 400; }
.preference-editor textarea { min-height: 104px; font-weight: 400; }
</style>
