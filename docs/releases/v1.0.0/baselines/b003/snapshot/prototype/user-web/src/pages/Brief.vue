<script setup lang="ts">
import { computed, onMounted, watch, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import { ArrowLeft, CalendarDays } from 'lucide-vue-next';
import { state } from '@shared/mock';
import EmptyState from '@shared/EmptyState.vue';
import NewsArticle from '../components/NewsArticle.vue';
const route = useRoute();
const brief = computed(() => state.briefs.find((b) => b.id === route.params.id));
async function scrollToHash() { await nextTick(); if (route.hash) document.getElementById(route.hash.slice(1))?.scrollIntoView({ block: 'start' }); }
onMounted(scrollToHash); watch(() => route.hash, scrollToHash);
</script>
<template>
  <div class="user-reading">
    <RouterLink to="/briefs" class="user-back"><ArrowLeft :size="16" aria-hidden="true" />历史简报</RouterLink>
    <EmptyState v-if="!brief" title="未找到这份简报"><RouterLink to="/today" class="button">返回今日简报</RouterLink></EmptyState>
    <template v-else>
      <header class="detail-header"><p class="detail-meta meta"><span><CalendarDays :size="14" :stroke-width="1.8" aria-hidden="true" />{{ brief.date }}</span><span class="badge">{{ brief.items.length }} 条新闻</span></p><h1>{{ brief.title }}</h1><p class="detail-summary">{{ brief.summary }}</p></header>
      <div v-if="brief.generationStatus === 'partial'" class="alert">部分来源暂不可用，已保留完成的内容。</div>
      <NewsArticle v-for="item in brief.items" :key="item.id" :item="item" expanded />
      <EmptyState v-if="!brief.items.length" title="本期没有匹配的新闻"><RouterLink to="/settings" class="button">调整订阅</RouterLink></EmptyState>
    </template>
  </div>
</template>
<style scoped>
.detail-header { border-bottom: 1px solid var(--color-border); padding-bottom: 24px; }
.detail-meta, .detail-meta > span { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.detail-meta { gap: 12px; }
.detail-header h1 { font-size: 30px; line-height: 42px; margin: 12px 0 16px; overflow-wrap: anywhere; }
.detail-summary { color: var(--color-text-secondary); font-size: 16px; line-height: 28px; margin-bottom: 12px; }
.detail-header + .alert { margin-top: 24px; }
@media (max-width: 767px) { .detail-header h1 { font-size: 24px; line-height: 34px; } }
</style>
