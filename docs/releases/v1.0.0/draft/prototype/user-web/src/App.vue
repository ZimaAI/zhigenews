<script setup lang="ts">
import { useRoute } from 'vue-router';
import ReaderShell from './components/ReaderShell.vue';
const route = useRoute();
</script>
<template>
  <RouterView v-if="route.meta.standalone" />
  <ReaderShell v-else><RouterView /></ReaderShell>
</template>
