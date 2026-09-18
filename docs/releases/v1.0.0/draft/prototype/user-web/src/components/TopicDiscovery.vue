<script setup lang="ts">
import type { Component } from 'vue';
import { Bot, BrainCircuit, Blocks, Lightbulb, ScanEye, Cpu, ShieldCheck, FlaskConical, Check, Plus } from 'lucide-vue-next';
import { TOPICS } from '@shared/mock';

const topicIcons: Record<string, Component> = {
  'Agent 工程': Bot, '大语言模型': BrainCircuit, '开源生态': Blocks, 'AI 产品': Lightbulb,
  '多模态': ScanEye, '算力与芯片': Cpu, 'AI 安全': ShieldCheck, '研究论文': FlaskConical,
};

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
    <legend>话题<span v-if="modelValue.length" class="topic-count">已选 {{ modelValue.length }}</span></legend>
    <div class="topic-options">
      <button v-for="topic in TOPICS" :key="topic" type="button" :aria-pressed="modelValue.includes(topic)" :disabled="disabled" @click="toggle(topic)">
        <span class="topic-icon"><component :is="topicIcons[topic]" :size="18" :stroke-width="1.8" aria-hidden="true" /></span><span class="topic-name">{{ topic }}</span><Check v-if="modelValue.includes(topic)" :size="14" aria-hidden="true" /><Plus v-else class="topic-add" :size="14" aria-hidden="true" />
      </button>
    </div>
    <p v-if="error" id="topic-error" class="user-field-error" role="alert">{{ error }}</p>
  </fieldset>
</template>

<style scoped>
.topic-picker { min-width: 0; border: 0; padding: 0; margin: 0; }
.topic-picker legend { font-size: 14px; font-weight: 500; margin-bottom: 12px; }
.topic-count { display: inline-flex; margin-left: 10px; padding: 2px 8px; border-radius: var(--radius-pill); background: var(--color-primary-soft); color: var(--color-primary); font-size: 11px; line-height: 18px; vertical-align: middle; }
.topic-options { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.topic-options button { display: grid; grid-template-columns: 28px minmax(0, 1fr) 14px; align-items: center; gap: 8px; min-width: 0; min-height: 60px; padding: 10px; border: 1px solid var(--color-border-control); border-radius: var(--radius-card); color: var(--color-text-secondary); background: var(--color-surface); font-size: 13px; text-align: left; }
.topic-options button:hover:not(:disabled) { border-color: var(--color-primary); background: var(--color-surface-muted); }
.topic-options button[aria-pressed="true"] { background: var(--color-primary-soft); border-color: var(--color-primary); color: var(--color-primary); }
.topic-icon { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 6px; background: var(--color-surface-muted); color: var(--color-text-secondary); }
.topic-options button[aria-pressed="true"] .topic-icon { background: var(--color-surface); color: var(--color-primary); }
.topic-name { overflow-wrap: anywhere; line-height: 20px; }
.topic-add { color: var(--color-text-muted); }
.topic-picker > p { margin: 8px 0 0; }
@media (max-width: 600px) { .topic-options { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 380px) { .topic-options button { grid-template-columns: 20px minmax(0, 1fr) 12px; padding: 8px; gap: 4px; font-size: 12px; } .topic-icon { width: 20px; height: 28px; } }
</style>
