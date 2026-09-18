<script setup lang="ts">
import { Check, Plus } from 'lucide-vue-next';
import { TOPICS } from '@shared/mock';

const props = defineProps<{ modelValue: string[]; error?: string; disabled?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [topics: string[]] }>();
function toggle(topic: string) {
  if (props.disabled) return;
  emit('update:modelValue', props.modelValue.includes(topic)
    ? props.modelValue.filter((value) => value !== topic)
    : [...props.modelValue, topic]);
}
</script>

<template>
  <fieldset id="topic-options" class="topic-picker" tabindex="-1" :aria-describedby="error ? 'topic-error' : undefined">
    <legend>话题</legend>
    <div class="topic-options">
      <button v-for="topic in TOPICS" :key="topic" type="button" :aria-pressed="modelValue.includes(topic)" :disabled="disabled" @click="toggle(topic)">
        <span>{{ topic }}</span><Check v-if="modelValue.includes(topic)" :size="15" aria-hidden="true" /><Plus v-else :size="15" aria-hidden="true" />
      </button>
    </div>
    <p v-if="error" id="topic-error" class="user-field-error" role="alert">{{ error }}</p>
  </fieldset>
</template>

<style scoped>
.topic-picker { min-width: 0; border: 0; padding: 0; margin: 0; }
.topic-picker legend { font-size: 14px; font-weight: 500; margin-bottom: 12px; }
.topic-options { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.topic-options button { display: flex; align-items: center; justify-content: space-between; gap: 6px; min-width: 0; min-height: 44px; padding: 10px 12px; border: 1px solid var(--color-border-control); border-radius: var(--radius-control); color: var(--color-text-secondary); background: var(--color-surface); font-size: 13px; text-align: left; }
.topic-options button:hover { border-color: var(--color-primary); }
.topic-options button[aria-pressed="true"] { background: var(--color-primary-soft); border-color: var(--color-primary); color: var(--color-primary); }
.topic-options button span { overflow-wrap: anywhere; }
.topic-picker > p { margin: 8px 0 0; }
@media (max-width: 600px) { .topic-options { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
