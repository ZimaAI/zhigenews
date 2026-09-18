<script setup lang="ts">
import { ref } from 'vue';
import { Plus, X } from 'lucide-vue-next';
const props = defineProps<{ modelValue: string[]; id: string; label: string; description: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>();
const input = ref('');
const error = ref('');
function add() {
  const values = input.value.split(/[,，;；\n]+/).map((v) => v.trim()).filter(Boolean);
  const merged = [...new Set([...props.modelValue, ...values])];
  if (merged.length > 20) { error.value = '最多添加 20 个关键词，请减少后重试。'; return; }
  if (values.some((v) => v.length > 80)) { error.value = '单个关键词不能超过 80 个字符。'; return; }
  emit('update:modelValue', merged); input.value = ''; error.value = '';
}
function remove(value: string) { emit('update:modelValue', props.modelValue.filter((item) => item !== value)); }
</script>
<template>
  <div class="field">
    <label :for="id">{{ label }}</label>
    <p :id="`${id}-help`" class="meta keyword-help">{{ description }} 最多 20 个，用逗号分隔后按 Enter 添加。</p>
    <div class="keyword-input-row"><input :id="id" v-model="input" class="field-control" :aria-describedby="`${id}-help ${id}-error`" :aria-invalid="!!error" placeholder="输入关键词" @keydown.enter.prevent="add" @input="error = ''" /><button class="button" type="button" :disabled="!input.trim()" @click="add"><Plus :size="16" aria-hidden="true" />添加</button></div>
    <p v-if="error" :id="`${id}-error`" class="user-field-error" role="alert">{{ error }}</p>
    <ul v-if="modelValue.length" class="keyword-list user-plain-list"><li v-for="value in modelValue" :key="value" class="keyword-token"><span>{{ value }}</span><button type="button" :aria-label="`移除关键词 ${value}`" @click="remove(value)"><X :size="14" aria-hidden="true" /></button></li></ul>
  </div>
</template>
<style scoped>
.keyword-help { margin: 0 0 8px; }
.keyword-input-row { display: flex; gap: 8px; min-width: 0; }
.keyword-input-row input { flex: 1; }
.keyword-input-row .button { flex: 0 0 auto; }
.keyword-list { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.keyword-token { display: inline-flex; align-items: center; gap: 4px; padding-left: 12px; border: 1px solid var(--color-border); border-radius: var(--radius-card); background: var(--color-surface-muted); font-size: 13px; min-width: 0; max-width: 100%; }
.keyword-token span { overflow-wrap: anywhere; }
.keyword-token button { display: flex; align-items: center; justify-content: center; border: 0; color: var(--color-text-secondary); background: none; width: 36px; min-width: 36px; height: 36px; cursor: pointer; border-radius: var(--radius-card); }
@media (max-width: 767px) { .keyword-token button { width: 44px; min-width: 44px; height: 44px; } }
</style>
