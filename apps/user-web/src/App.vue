<script setup lang="ts">
import { watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { sessionState } from './state';
import ReaderShell from './components/ReaderShell.vue';
const route = useRoute(), router = useRouter();
watch(() => sessionState.session, session => {
  if (!session && !route.meta.standalone) void router.replace({ path: '/login', query: { next: route.fullPath } });
});
</script>
<template><RouterView v-if="route.meta.standalone" /><ReaderShell v-else><RouterView /></ReaderShell></template>
