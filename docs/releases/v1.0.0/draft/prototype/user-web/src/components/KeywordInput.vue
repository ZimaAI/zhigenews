<script setup lang="ts">
import { computed, ref } from 'vue';
import { Hash, Plus, X } from 'lucide-vue-next';
const props = defineProps<{ modelValue: string[]; id: string; label: string; description?: string; disabled?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>();
const input = ref('');
const error = ref('');
const pending = computed(() => !!input.value.trim());
function invalid(message: string): false {
  error.value = message;
  document.getElementById(props.id)?.focus();
  return false;
}
function add(): boolean {
  if (props.disabled) return false;
  const values = input.value.split(/[,，;；\n]+/).map((value) => value.trim()).filter(Boolean);
  const merged = [...new Set([...props.modelValue, ...values])];
  if (merged.length > 20) return invalid('最多添加 20 个关键词。');
  if (values.some((value) => value.length > 80)) return invalid('每个关键词最多 80 个字符。');
  emit('update:modelValue', merged);
  input.value = '';
  error.value = '';
  return true;
}
function remove(value: string) {
  if (!props.disabled) emit('update:modelValue', props.modelValue.filter((item) => item !== value));
}
function enter(event: KeyboardEvent) { if (!event.isComposing) { event.preventDefault(); add(); } }
defineExpose({ flush: add, pending });
</script>
<template>
  <div class="field">
    <label :for="id">{{ label }}</label>
    <div class="keyword-input-row"><input :id="id" v-model="input" class="field-control" :disabled="disabled" :aria-describedby="error ? `${id}-error` : undefined" :aria-invalid="!!error" placeholder="输入关键词，按回车添加" @keydown.enter="enter" @input="error = ''" /><button class="button" type="button" :disabled="disabled || !pending" aria-label="添加关键词" @click="add"><Plus :size="17" aria-hidden="true" /><span>添加</span></button></div>
    <p v-if="error" :id="`${id}-error`" class="user-field-error" role="alert">{{ error }}</p>
    <ul v-if="modelValue.length" class="keyword-list user-plain-list"><li v-for="value in modelValue" :key="value" class="keyword-token"><Hash :size="13" :stroke-width="1.8" aria-hidden="true" /><span>{{ value }}</span><button type="button" :disabled="disabled" :aria-label="`移除关键词 ${value}`" @click="remove(value)"><X :size="14" aria-hidden="true" /></button></li></ul>
  </div>
</template>
<style scoped>
.keyword-input-row { display: flex; gap: 8px; min-width: 0; }
.keyword-input-row input { flex: 1; min-width: 0; }
.keyword-input-row .button { flex: 0 0 auto; min-height: 44px; }
.keyword-list { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
.keyword-token { display: inline-flex; align-items: center; gap: 5px; padding-left: 12px; border: 1px solid var(--color-primary-border); border-radius: var(--radius-pill); background: var(--color-primary-soft); color: var(--color-primary); font-size: 13px; font-weight: 400; min-width: 0; max-width: 100%; }
.keyword-token > svg { flex-shrink: 0; }
.keyword-token span { overflow-wrap: anywhere; }
.keyword-token button { display: flex; align-items: center; justify-content: center; border: 0; color: var(--color-primary); background: none; width: 44px; min-width: 44px; height: 44px; border-radius: var(--radius-pill); }
.keyword-token button:hover:not(:disabled) { background: var(--color-surface); }
.user-field-error { margin: 0; }
</style>
