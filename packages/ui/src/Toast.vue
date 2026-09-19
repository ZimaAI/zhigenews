<script setup lang="ts">
import { notification } from './notifications';
</script>
<template><div v-if="notification" class="toast" role="status" aria-live="polite">{{ notification }}</div></template>
