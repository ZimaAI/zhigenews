<script setup lang="ts">
import { Inbox, CircleAlert } from 'lucide-vue-next';
defineProps<{ title: string; description?: string; error?: boolean }>();
</script>
<template><section class="empty-state" :role="error ? 'alert' : undefined"><component :is="error ? CircleAlert : Inbox" :size="32" :stroke-width="1.6" aria-hidden="true" /><h2>{{ title }}</h2><p v-if="description">{{ description }}</p><div class="actions"><slot /></div></section></template>
