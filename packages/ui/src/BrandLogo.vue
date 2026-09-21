<script setup lang="ts">
const robinUrl = `${import.meta.env.BASE_URL}zhige-robin.svg`;

withDefaults(defineProps<{ size?: number; decorative?: boolean }>(), {
  size: 40,
  decorative: false,
});
</script>

<template>
  <img class="zhige-logo" :src="robinUrl" :width="size" :height="size"
    :style="{ width: `${size}px`, height: `${size}px` }"
    :alt="decorative ? '' : '知更'" :aria-hidden="decorative ? true : undefined" />
</template>

<style scoped>
.zhige-logo { display: block; flex-shrink: 0; object-fit: contain; }
</style>
