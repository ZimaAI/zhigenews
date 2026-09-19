<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch, useId } from 'vue';
import { X } from 'lucide-vue-next';
const props = defineProps<{ open: boolean; title: string }>();
const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLDialogElement>();
const titleId = useId();
let opener: HTMLElement | null = null;
function trapTab(event: KeyboardEvent) {
  if (event.key !== 'Tab' || event.defaultPrevented || !dialog.value?.open) return;
  const element = dialog.value;
  const focusable = Array.from(element.querySelectorAll<HTMLElement>('a[href], area[href], button, input, select, textarea, summary, iframe, [tabindex], [contenteditable="true"]'))
    .filter(node => node.tabIndex >= 0 && !node.matches(':disabled') && !node.closest('[hidden], [inert], [aria-hidden="true"]') && node.getClientRects().length > 0 && getComputedStyle(node).visibility === 'visible');
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (!first || !last) { event.preventDefault(); element.focus(); return; }
  const active = document.activeElement;
  if (active === element || !element.contains(active) || (event.shiftKey ? active === first : active === last)) {
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  }
}
watch(() => props.open, async (open) => {
  await nextTick();
  if (open && !dialog.value?.open) { opener = document.activeElement as HTMLElement; dialog.value?.showModal(); }
  else if (!open && dialog.value?.open) { dialog.value.close(); opener?.focus(); }
}, { immediate: true });
onBeforeUnmount(() => { if (dialog.value?.open) dialog.value.close(); });
</script>
<template><Teleport to="body"><dialog ref="dialog" class="modal" :aria-labelledby="titleId" @keydown="trapTab" @cancel.prevent="emit('close')" @click="e => { if(e.target === dialog) emit('close') }"><header class="modal-header"><h2 :id="titleId">{{ title }}</h2><button class="button button--ghost icon-button" aria-label="关闭弹窗" @click="emit('close')"><X :size="20" /></button></header><div class="modal-body"><slot /></div><footer v-if="$slots.footer" class="modal-footer"><slot name="footer" /></footer></dialog></Teleport></template>
