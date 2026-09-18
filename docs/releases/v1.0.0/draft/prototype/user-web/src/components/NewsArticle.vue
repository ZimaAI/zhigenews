<script setup lang="ts">
import { ref } from 'vue';
import { Check, ExternalLink, ArrowUpRight } from 'lucide-vue-next';
import { api, formatDate } from '@shared/mock';
import type { NewsItem } from '@shared/types';
const props = defineProps<{ item: NewsItem; briefId: string; expanded?: boolean }>();
const busy = ref(false), error = ref('');
async function mark() { if (busy.value) return; busy.value = true; error.value = ''; try { await api.markRead(props.item.id); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
function domain(url: string) { try { return new URL(url).hostname; } catch { return '来源地址待确认'; } }
</script>
<template>
  <article class="news-article" :class="{ expanded }" :id="`news-${item.id}`">
    <div class="news-meta"><span>{{ item.source }}</span><span aria-hidden="true">·</span><time v-if="item.publishedAt" :datetime="item.publishedAt">{{ formatDate(item.publishedAt) }}</time><span v-else>时间未知</span><span class="topic-label">{{ item.topic }}</span></div>
    <h2 v-if="expanded">{{ item.title }}</h2>
    <h2 v-else><RouterLink :to="`/briefs/${briefId}#news-${item.id}`">{{ item.title }}</RouterLink></h2>
    <p class="news-summary">{{ item.summary }}</p>
    <p v-if="expanded" class="news-reason">{{ item.reason }}</p>
    <div class="news-actions"><RouterLink v-if="!expanded" class="user-inline-link" :to="`/briefs/${briefId}#news-${item.id}`">阅读详情<ArrowUpRight :size="14" aria-hidden="true" /></RouterLink><a v-else :href="item.url" target="_blank" rel="noopener noreferrer" class="user-inline-link">查看来源<ExternalLink :size="14" aria-hidden="true" /><span class="sr-only">（新标签页）</span></a><button class="read-button" :class="{ 'is-read': item.read }" :disabled="busy" :aria-pressed="item.read" :aria-label="item.read ? '标为未读' : '标为已读'" @click="mark"><Check :size="15" aria-hidden="true" />{{ busy ? '更新中…' : item.read ? '已读' : '标为已读' }}</button></div>
    <p v-if="error" class="user-field-error" role="alert">{{ error }} <button class="button button--ghost" :disabled="busy" @click="mark">重试</button></p>
    <details v-if="expanded" class="citation-section"><summary>关联来源 · {{ item.citations.length }}</summary><p v-if="!item.citations.length" class="meta">暂无关联来源</p><ol v-else class="citation-list"><li v-for="citation in item.citations" :key="citation.id"><a :href="citation.url" target="_blank" rel="noopener noreferrer">{{ citation.title }}<ExternalLink :size="13" aria-hidden="true" /><span class="sr-only">（新标签页）</span></a><p class="meta">{{ citation.name }} · {{ domain(citation.url) }}</p></li></ol></details>
  </article>
</template>
<style scoped>
.news-article { padding: 28px 0; border-bottom: 1px solid var(--color-border); scroll-margin-top: 24px; }
.news-article:last-child { border-bottom: 0; }
.news-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; color: var(--color-text-muted); font-size: 12px; line-height: 20px; }
.topic-label { margin-left: auto; color: var(--color-primary); }
h2 { margin: 12px 0 8px; font-size: 18px; line-height: 28px; font-weight: 600; overflow-wrap: anywhere; }
h2 a { color: var(--color-text); text-decoration: none; }
h2 a:hover { color: var(--color-primary); text-decoration: underline; text-underline-offset: 4px; }
.news-summary { margin: 0; color: var(--color-text-secondary); font-size: 16px; line-height: 27px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.news-reason { margin: 12px 0 0; color: var(--color-text-muted); font-size: 13px; line-height: 22px; }
.news-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.user-inline-link, .read-button { min-height: 44px; }
.read-button { border: 0; background: none; padding: 8px 0 8px 8px; color: var(--color-text-muted); font: inherit; font-size: 13px; display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.read-button:disabled { opacity: .65; cursor: wait; }
.read-button:hover, .read-button.is-read { color: var(--color-primary); }
.expanded { padding-block: 32px; }
.expanded h2 { margin-block: 16px; font-size: 20px; line-height: 32px; }
.expanded .news-summary { display: block; font-size: 18px; line-height: 32px; }
.citation-section { margin-top: 12px; font-size: 13px; }
.citation-section summary { color: var(--color-text-secondary); cursor: pointer; min-height: 44px; padding-block: 12px; }
.citation-list { padding-left: 20px; margin: 0; }
.citation-list li { padding-left: 4px; margin-block: 12px; }
.citation-list a { text-underline-offset: 3px; overflow-wrap: anywhere; }
.citation-list svg { vertical-align: middle; margin-left: 6px; }
.citation-list p { margin: 4px 0 0; overflow-wrap: anywhere; }
@media (max-width: 767px) { .news-article { padding-block: 24px; } .expanded .news-summary { font-size: 17px; line-height: 30px; } .topic-label { margin-left: 0; } }
</style>
