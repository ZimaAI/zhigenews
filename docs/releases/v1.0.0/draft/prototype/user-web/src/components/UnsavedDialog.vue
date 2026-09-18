<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import Modal from '@shared/Modal.vue';
const props = defineProps<{ dirty: boolean }>();
const open = ref(false);
let resolve: ((leave: boolean) => void) | undefined;
onBeforeRouteLeave(() => {
  if (!props.dirty) return true;
  open.value = true;
  return new Promise<boolean>((r) => { resolve = r; });
});
function finish(leave: boolean) { open.value = false; resolve?.(leave); resolve = undefined; }
function beforeUnload(event: BeforeUnloadEvent) { if (props.dirty) { event.preventDefault(); event.returnValue = ''; } }
onMounted(() => window.addEventListener('beforeunload', beforeUnload));
onBeforeUnmount(() => { window.removeEventListener('beforeunload', beforeUnload); resolve?.(false); });
</script>
<template>
  <Modal :open="open" title="还有未保存的修改" @close="finish(false)">
    <p>离开后，这次编辑不会应用到你的订阅。可以留下继续编辑，或放弃修改。</p>
    <template #footer><button class="button" @click="finish(true)">放弃修改并离开</button><button class="button button--primary" @click="finish(false)">继续编辑</button></template>
  </Modal>
</template>
