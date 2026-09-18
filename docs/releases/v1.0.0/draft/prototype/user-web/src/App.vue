<script setup lang="ts">
import { watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { state } from '@shared/mock';
import ReaderShell from './components/ReaderShell.vue';
const route = useRoute();
const router = useRouter();
watch(() => state.onboardingCompleted, completed => {
  if (!completed && state.authenticated && !route.meta.standalone && route.path !== '/onboarding') void router.replace('/onboarding');
}, { flush: 'post' });
</script>
<template>
  <RouterView v-if="route.meta.standalone" />
  <ReaderShell v-else><RouterView /></ReaderShell>
</template>
