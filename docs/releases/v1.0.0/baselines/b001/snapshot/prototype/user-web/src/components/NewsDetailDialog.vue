<script setup lang="ts">
import { Clock3, ExternalLink } from 'lucide-vue-next';
import Modal from '@shared/Modal.vue';
import { formatDate } from '@shared/mock';
import type { NewsItem } from '@shared/types';
defineProps<{ item: NewsItem; open: boolean }>();
defineEmits<{ close: [] }>();
function domain(url: string) { try { return new URL(url).hostname; } catch { return '来源地址待确认'; } }
</script>
<template>
  <Modal :open="open" :title="item.title" @close="$emit('close')">
    <div class="news-detail">
      <div class="detail-meta"><span>{{ item.source }}</span><span class="detail-time"><Clock3 :size="13" :stroke-width="1.8" aria-hidden="true" /><time v-if="item.publishedAt" :datetime="item.publishedAt">{{ formatDate(item.publishedAt) }}</time><span v-else>时间未知</span></span><span class="detail-topic">{{ item.topic }}</span></div>
      <p class="detail-summary">{{ item.summary }}</p>
      <p v-if="item.reason" class="detail-reason">{{ item.reason }}</p>
      <a class="detail-source" :href="item.url" target="_blank" rel="noopener noreferrer"><ExternalLink :size="16" :stroke-width="1.8" aria-hidden="true" />查看来源<span class="sr-only">（新标签页）</span></a>
      <section v-if="item.citations.length" class="detail-citations" aria-label="关联来源">
        <h3>关联来源</h3>
        <ol><li v-for="citation in item.citations" :key="citation.id"><a :href="citation.url" target="_blank" rel="noopener noreferrer">{{ citation.title }}<ExternalLink :size="13" :stroke-width="1.8" aria-hidden="true" /><span class="sr-only">（新标签页）</span></a><p>{{ citation.name }} · {{ domain(citation.url) }}</p></li></ol>
      </section>
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
.news-detail .detail-reason { margin-block: 16px; color: var(--color-text-secondary); font-size: 14px; line-height: 24px; }
.news-detail .detail-source { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; font-size: 14px; }
.news-detail .detail-citations { margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--color-border); }
.news-detail .detail-citations h3 { font-size: 14px; }
.news-detail .detail-citations ol { margin: 0; padding-left: 20px; }
.news-detail .detail-citations li { padding-left: 4px; margin-top: 12px; font-size: 14px; }
.news-detail .detail-citations li a { display: inline-block; min-height: 44px; padding-block: 10px; }
.news-detail .detail-citations li a svg { margin-left: 6px; vertical-align: middle; }
.news-detail .detail-citations li p { margin: 0; color: var(--color-text-muted); font-size: 12px; }
@media (max-width: 767px) { .modal:has(.news-detail) .modal-header h2 { font-size: 18px; line-height: 28px; } .news-detail .detail-summary { font-size: 17px; line-height: 30px; } }
</style>
