<script setup lang="ts">
import { computed } from 'vue';
import { statusLabel } from './format';
const props = defineProps<{ status: string }>();
const tone = computed(() => ['failed'].includes(props.status) ? 'danger' : ['partial', 'unverified', 'unknown', 'pending'].includes(props.status) ? 'warning' : ['completed', 'healthy', 'active', 'published', 'verified', 'submitted', 'success'].includes(props.status) ? 'success' : ['running', 'syncing', 'queued', 'cancelling'].includes(props.status) ? 'primary' : 'neutral');
</script>
<template><span class="badge" :class="`badge--${tone}`"><span class="badge-dot" aria-hidden="true"></span>{{ statusLabel(status) }}</span></template>
