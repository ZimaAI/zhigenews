<script setup lang="ts">
import { Clock3, ExternalLink } from 'lucide-vue-next';
import Modal from '@ui/Modal.vue';
import { formatDate, safeExternalUrl } from '../state';
import type { NewsItem } from '@zhigenews/api-client';
defineProps<{ item: NewsItem; open: boolean }>();
defineEmits<{ close: [] }>();
</script>
<template>
  <Modal :open="open" :title="item.title" @close="$emit('close')">
    <div class="news-detail">
      <div class="detail-meta"><span>{{ item.source }}</span><span class="detail-time"><Clock3 :size="13" :stroke-width="1.8" aria-hidden="true" /><time v-if="item.publishedAt" :datetime="item.publishedAt">{{ formatDate(item.publishedAt) }}</time><span v-else>时间未知</span></span><span class="detail-topic">{{ item.topic }}</span></div>
      <p class="detail-summary">{{ item.summary }}</p>
      <p class="meta">采集于 <time :datetime="item.fetchedAt">{{ formatDate(item.fetchedAt) }}</time></p>
      <a class="detail-source" :href="safeExternalUrl(item.url)" target="_blank" rel="noopener noreferrer"><ExternalLink :size="16" :stroke-width="1.8" aria-hidden="true" />查看来源<span class="sr-only">（新标签页）</span></a>
    </div>
  </Modal>
</template>
<style>
.modal:has(.news-detail) { width: min(760px, calc(100vw - 32px)); overflow: auto; overscroll-behavior: contain; }
.modal:has(.news-detail) .modal-header { position: sticky; top: 0; z-index: 1; align-items: flex-start; background: var(--color-surface); }
.modal:has(.news-detail) .modal-header h2 { padding-block: 6px; font-size: 22px; line-height: 32px; overflow-wrap: anywhere; }
.modal:has(.news-detail) .icon-button { min-width: 44px; min-height: 44px; flex-shrink: 0; }
.news-detail { min-width: 0; overflow-wrap: anywhere; }
.news-detail .detail-meta { display: flex; align-items: center; gap: 8px 12px; flex-wrap: wrap; margin-bottom: 24px; color: var(--color-text-muted); font-size: 13px; }
.news-detail .detail-time { display: inline-flex; align-items: center; gap: 6px; }
.news-detail .detail-topic { padding: 3px 10px; border-radius: var(--radius-pill); color: var(--color-primary); background: var(--color-primary-soft); }
.news-detail .detail-summary { font-size: 18px; line-height: 32px; white-space: pre-line; }
.news-detail .detail-source { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; font-size: 14px; }
@media (max-width: 767px) { .modal:has(.news-detail) .modal-header h2 { font-size: 18px; line-height: 28px; } .news-detail .detail-summary { font-size: 17px; line-height: 30px; } }
</style>
