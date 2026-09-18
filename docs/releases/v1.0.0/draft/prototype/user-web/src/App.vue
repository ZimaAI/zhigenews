<script setup lang="ts">
import { useRoute } from 'vue-router';
import AppShell from '@shared/AppShell.vue';
const route = useRoute();
</script>
<template>
  <RouterView v-if="route.meta.standalone" />
  <AppShell v-else app="user"><RouterView /></AppShell>
</template>
