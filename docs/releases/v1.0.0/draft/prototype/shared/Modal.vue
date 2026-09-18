<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch, useId } from 'vue';
import { X } from 'lucide-vue-next';
const props = defineProps<{ open: boolean; title: string }>();
const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLDialogElement>();
const titleId = useId();
let opener: HTMLElement | null = null;
watch(() => props.open, async (open) => {
  await nextTick();
  if (open && !dialog.value?.open) { opener = document.activeElement as HTMLElement; dialog.value?.showModal(); }
  else if (!open && dialog.value?.open) { dialog.value.close(); opener?.focus(); }
}, { immediate: true });
onBeforeUnmount(() => { if (dialog.value?.open) dialog.value.close(); });
</script>
<template><Teleport to="body"><dialog ref="dialog" class="modal" :aria-labelledby="titleId" @cancel.prevent="emit('close')" @click="e => { if(e.target === dialog) emit('close') }"><header class="modal-header"><h2 :id="titleId">{{ title }}</h2><button class="button button--ghost icon-button" aria-label="关闭弹窗" @click="emit('close')"><X :size="20" /></button></header><div class="modal-body"><slot /></div><footer v-if="$slots.footer" class="modal-footer"><slot name="footer" /></footer></dialog></Teleport></template>
