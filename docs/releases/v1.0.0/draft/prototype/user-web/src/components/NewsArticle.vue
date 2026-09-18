<script setup lang="ts">
import { ref } from 'vue';
import { Check, ExternalLink, ArrowUpRight, BookOpen } from 'lucide-vue-next';
import { api, formatDate } from '@shared/mock';
import type { NewsItem } from '@shared/types';
const props = defineProps<{ item: NewsItem; briefId: string; expanded?: boolean; index?: number }>();
const busy = ref(false), error = ref('');
async function mark() { if (busy.value) return; busy.value = true; error.value = ''; try { await api.markRead(props.item.id); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
function domain(url: string) { try { return new URL(url).hostname; } catch { return '来源地址待确认'; } }
</script>
<template>
  <article class="news-article" :class="{ expanded }" :id="`news-${item.id}`">
    <div class="news-meta"><span class="source-letter" aria-hidden="true">{{ item.source.charAt(0) }}</span><span>{{ item.source }}</span><span aria-hidden="true">·</span><span>{{ item.sourceType === 'search' ? '网络检索' : item.sourceType === 'newsnow' ? 'NewsNow' : 'RSS' }}</span><time v-if="item.publishedAt" :datetime="item.publishedAt">{{ formatDate(item.publishedAt) }}（示例）</time><span v-else>发布时间未知</span><span class="topic-label">{{ item.topic }}</span><span class="read-label">{{ item.read ? '已读' : '未读' }}</span></div>
    <h2 v-if="expanded">{{ item.title }}</h2>
    <h2 v-else><RouterLink :to="`/briefs/${briefId}#news-${item.id}`">{{ item.title }}</RouterLink></h2>
    <p class="news-summary">{{ item.summary }}</p>
    <div class="news-reason"><BookOpen :size="14" aria-hidden="true" /><span>{{ item.reason }}</span></div>
    <div class="news-actions"><RouterLink v-if="!expanded" class="user-inline-link" :to="`/briefs/${briefId}#news-${item.id}`">阅读全文与 {{ item.citations.length }} 条关联来源<ArrowUpRight :size="14" aria-hidden="true" /></RouterLink><a v-else :href="item.url" target="_blank" rel="noopener noreferrer" class="user-inline-link">查看参考原文<ExternalLink :size="14" aria-hidden="true" /><span class="sr-only">（新标签页）</span></a><button class="read-button" :disabled="busy" @click="mark"><Check :size="15" aria-hidden="true" />{{ busy ? '正在更新…' : item.read ? '撤销已读' : '标记已读' }}</button></div>
    <p v-if="error" class="user-field-error" role="alert">{{ error }} <button class="button button--ghost" :disabled="busy" @click="mark">重试</button></p>
    <div v-if="expanded" class="citation-section"><h3>关联来源 <span class="meta">{{ item.citations.length }} 条引用</span></h3><p v-if="!item.citations.length" class="alert">此条摘要缺少可用引用，请谨慎使用；原型仍保留内容以便评审。</p><ol v-else class="citation-list"><li v-for="citation in item.citations" :key="citation.id"><a :href="citation.url" target="_blank" rel="noopener noreferrer">{{ citation.title }}<ExternalLink :size="13" aria-hidden="true" /><span class="sr-only">（新标签页）</span></a><p class="meta">{{ citation.name }} · {{ domain(citation.url) }} · {{ citation.publishedAt || '原文时间未确认' }}</p></li></ol><p class="meta">内容是用于交互评审的模拟摘要，引用链接为公开参考资料，不代表今日最新报道或独立核实。</p></div>
  </article>
</template>
<style scoped>
.news-article { padding: 24px; border-bottom: 1px solid var(--color-border); scroll-margin-top: 100px; }
.news-article:last-child { border-bottom: 0; }
.news-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; color: var(--color-text-muted); font-size: 12px; line-height: 20px; }
.source-letter { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; border: 1px solid var(--color-border); border-radius: 6px; color: var(--color-text-secondary); font-size: 11px; background: var(--color-surface-muted); }
.topic-label { margin-left: auto; color: var(--color-primary); }
.read-label { font-size: 11px; }
h2 { margin: 12px 0 8px; font-size: 18px; line-height: 28px; font-weight: 600; overflow-wrap: anywhere; }
h2 a { color: var(--color-text); text-decoration: none; }
h2 a:hover { color: var(--color-primary); text-decoration: underline; text-underline-offset: 4px; }
.news-summary { margin: 0 0 16px; color: var(--color-text-secondary); font-size: 16px; line-height: 26px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.news-reason { display: flex; align-items: baseline; gap: 8px; color: var(--color-text-muted); font-size: 13px; line-height: 20px; }
.news-reason svg { flex-shrink: 0; }
.news-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.read-button { border: 0; background: none; padding: 8px 0; min-height: 36px; color: var(--color-text-muted); font: inherit; font-size: 13px; display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.read-button:disabled { color: var(--color-text-disabled); cursor: wait; }
.read-button:hover { color: var(--color-primary); }
.expanded { padding: 32px 0; }
.expanded h2 { margin-block: 16px; font-size: 20px; line-height: 32px; }
.expanded .news-summary { display: block; font-size: 18px; line-height: 32px; }
.citation-section { padding: 16px; background: var(--color-surface-muted); border-radius: 8px; margin-top: 24px; }
.citation-section h3 { font-size: 14px; margin: 0 0 12px; }
.citation-section h3 span { margin-left: 8px; font-weight: 400; }
.citation-section > p:last-child { margin-bottom: 0; }
.citation-list { padding-left: 20px; margin: 0; }
.citation-list li { padding-left: 4px; margin-block: 12px; font-size: 13px; }
.citation-list a { text-underline-offset: 3px; overflow-wrap: anywhere; }
.citation-list svg { vertical-align: middle; margin-left: 6px; }
.citation-list p { margin: 4px 0 0; overflow-wrap: anywhere; }
@media (max-width: 767px) { .news-article { padding: 20px 16px; } .expanded { padding: 24px 0; } .expanded .news-summary { font-size: 17px; line-height: 30px; } .read-button { min-height: 44px; } }
</style>
