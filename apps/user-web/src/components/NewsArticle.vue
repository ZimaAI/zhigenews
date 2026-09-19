<script setup lang="ts">
import { ref } from 'vue';
import { BookOpen, Clock3 } from 'lucide-vue-next';
import { formatDate } from '../state';
import type { NewsItem } from '@zhigenews/api-client';
import NewsDetailDialog from './NewsDetailDialog.vue';
defineProps<{ item: NewsItem; expanded?: boolean }>();
const detailOpen = ref(false);
</script>
<template>
  <article class="news-article" :class="{ expanded }" :id="`news-${item.id}`">
    <div class="news-meta"><span class="news-source">{{ item.source }}</span><span class="news-time"><Clock3 :size="13" :stroke-width="1.8" aria-hidden="true" /><time v-if="item.publishedAt" :datetime="item.publishedAt">{{ formatDate(item.publishedAt) }}</time><span v-else>时间未知</span></span><span class="topic-label">{{ item.topic }}</span></div>
    <h2><button class="news-title" aria-haspopup="dialog" :aria-expanded="detailOpen" @click="detailOpen = true">{{ item.title }}</button></h2>
    <p class="news-summary">{{ item.summary }}</p>
    <p v-if="expanded" class="news-reason">{{ item.reason }}</p>
    <div class="news-actions"><button class="user-inline-link detail-button" aria-haspopup="dialog" :aria-expanded="detailOpen" @click="detailOpen = true"><BookOpen :size="16" :stroke-width="1.8" aria-hidden="true" />阅读详情</button></div>
    <NewsDetailDialog :item="item" :open="detailOpen" @close="detailOpen = false" />
  </article>
</template>
<style scoped>
.news-article { padding: 28px 0; border-bottom: 1px solid var(--color-border); scroll-margin-top: 24px; }
.news-article:last-child { border-bottom: 0; }
.news-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; color: var(--color-text-muted); font-size: 12px; line-height: 20px; }
.news-source, .news-time { display: inline-flex; align-items: center; gap: 6px; min-width: 0; overflow-wrap: anywhere; }
.news-time svg { flex-shrink: 0; }
.topic-label { margin-left: auto; padding: 3px 10px; border-radius: var(--radius-pill); background: var(--color-primary-soft); color: var(--color-primary); overflow-wrap: anywhere; }
h2 { margin: 12px 0 8px; font-size: 18px; line-height: 28px; font-weight: 600; overflow-wrap: anywhere; }
.news-title { display: block; width: 100%; min-height: 44px; padding: 4px 0; border: 0; background: none; color: var(--color-text); text-align: left; font: inherit; overflow-wrap: anywhere; }
.news-title:hover { color: var(--color-primary); text-decoration: underline; text-underline-offset: 4px; }
.news-summary { margin: 0; color: var(--color-text-secondary); font-size: 16px; line-height: 27px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.news-reason { margin: 12px 0 0; color: var(--color-text-muted); font-size: 13px; line-height: 22px; }
.news-actions { margin-top: 12px; }
.detail-button { min-height: 44px; padding: 4px 0; border: 0; background: none; color: var(--color-primary); text-decoration: underline; font: inherit; font-size: 13px; }
.detail-button:hover { color: var(--color-primary-hover); }
.expanded { padding-block: 32px; }
.expanded h2 { margin-block: 16px; font-size: 20px; line-height: 32px; }
.expanded .news-summary { display: block; font-size: 18px; line-height: 32px; }
@media (max-width: 767px) { .news-article { padding-block: 24px; } .expanded .news-summary { font-size: 17px; line-height: 30px; } .topic-label { margin-left: 0; } }
</style>
