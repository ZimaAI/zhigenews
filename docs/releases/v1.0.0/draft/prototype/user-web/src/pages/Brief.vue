<script setup lang="ts">
import { computed, ref, onMounted, watch, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import { ArrowLeft, ArrowUpRight, RotateCw } from 'lucide-vue-next';
import { api, state, formatDate } from '@shared/mock';
import Badge from '@shared/Badge.vue';
import EmptyState from '@shared/EmptyState.vue';
import NewsArticle from '../components/NewsArticle.vue';
const route = useRoute();
const brief = computed(() => state.briefs.find((b) => b.id === route.params.id));
const delivery = computed(() => state.deliveries.find((d) => d.briefId === brief.value?.id));
const busy = ref(false), error = ref('');
async function retry() { if (busy.value || !brief.value) return; busy.value = true; error.value = ''; try { await api.retryDelivery(brief.value.id); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
async function scrollToHash() { await nextTick(); if (route.hash) document.getElementById(route.hash.slice(1))?.scrollIntoView({ block: 'start' }); }
onMounted(scrollToHash); watch(() => route.hash, scrollToHash);
</script>
<template>
  <div class="user-reading">
    <RouterLink to="/briefs" class="user-back"><ArrowLeft :size="16" aria-hidden="true" />返回历史简报</RouterLink>
    <EmptyState v-if="!brief" title="未找到这份简报" description="它可能不在当前演示场景中。可以返回今日简报，或切换到正常场景。"><RouterLink to="/today" class="button">查看今日简报</RouterLink></EmptyState>
    <template v-else>
      <header class="detail-header"><p class="eyebrow">DAILY BRIEF · {{ brief.date }} · V{{ brief.version }}</p><h1>{{ brief.title }}</h1><p class="detail-summary">{{ brief.summary }}</p><p class="meta">{{ formatDate(brief.generatedAt) }} 生成 · {{ brief.items.length }} 条内容 · 模拟摘要，非实时新闻报道</p><div class="user-status-line"><strong>生成结果</strong><Badge :status="brief.generationStatus" /><strong>外部推送</strong><Badge :status="brief.deliveryStatus" /><RouterLink class="user-inline-link" :to="`/runs/${brief.runId}`">查看整理过程<ArrowUpRight :size="14" aria-hidden="true" /></RouterLink></div></header>
      <div v-if="brief.generationStatus === 'partial'" class="alert">本期部分完成。可阅读已生成内容，来源缺失与预算限制见整理过程。</div>
      <NewsArticle v-for="item in brief.items" :key="item.id" :item="item" :brief-id="brief.id" expanded />
      <EmptyState v-if="!brief.items.length" title="本期没有匹配的内容" description="没有自动放宽筛选规则。可以调整关键词或新闻时间范围后重新生成。"><RouterLink to="/preferences" class="button">调整订阅</RouterLink></EmptyState>
      <section class="card brief-record"><h2>关于这一期</h2><details class="user-disclosure"><summary>生成时使用的兴趣订阅 · 版本 {{ brief.preferenceSnapshot.version }}</summary><div><dl class="user-key-values"><dt>关注方向</dt><dd>{{ brief.preferenceSnapshot.role || '未填写' }}</dd><dt>关注主题</dt><dd>{{ brief.preferenceSnapshot.topics.join('、') }}</dd><dt>包含关键词</dt><dd>{{ brief.preferenceSnapshot.keywords.join('、') || '无' }}</dd><dt>排除关键词</dt><dd>{{ brief.preferenceSnapshot.excludedKeywords.join('、') || '无' }}</dd><dt>匹配方式</dt><dd>{{ brief.preferenceSnapshot.keywordMode === 'required' ? '至少包含一个关键词' : '优先推荐关键词相关内容' }}</dd><dt>阅读偏好</dt><dd>{{ brief.preferenceSnapshot.windowHours }} 小时 · 最多 {{ brief.preferenceSnapshot.maxItems }} 条 · {{ brief.preferenceSnapshot.depth }}</dd></dl><p class="meta">这是历史快照。你现在修改订阅，只会影响下一次生成。</p></div></details><details class="user-disclosure"><summary>推送记录</summary><div class="stack"><div class="user-status-line"><strong>{{ delivery?.channel || '邮件' }}</strong><Badge :status="brief.deliveryStatus" /><span>{{ delivery?.destination || '未启用外部推送' }}</span></div><p class="meta">{{ delivery?.time || '暂无发送记录' }}<template v-if="delivery"> · 已尝试 {{ delivery.attempts }} 次</template></p><p v-if="delivery?.error" class="alert alert--danger">{{ delivery.error }}</p><p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p><button v-if="['failed', 'unknown'].includes(brief.deliveryStatus)" class="button" :disabled="busy" @click="retry"><RotateCw :size="15" aria-hidden="true" />{{ busy ? '正在提交重试…' : '重试推送同一期' }}</button><p class="meta">模拟投递不会发送真实邮件。“已提交发送”表示服务接收请求，不表示已送达。</p></div></details></section>
    </template>
  </div>
</template>
<style scoped>
.detail-header { border-bottom: 1px solid var(--color-border); padding-bottom: 32px; }
.detail-header h1 { font-size: 32px; line-height: 44px; margin: 12px 0 20px; overflow-wrap: anywhere; }
.detail-summary { color: var(--color-text-secondary); font-size: 18px; line-height: 32px; margin-bottom: 20px; }
.detail-header .user-status-line { margin-top: 20px; }
.detail-header .user-inline-link { margin-left: auto; }
.brief-record { margin-top: 24px; }
.brief-record h2 { font-size: 20px; margin-top: 0; }
.brief-record .user-disclosure:first-of-type { margin-top: 0; }
.brief-record button { align-self: flex-start; }
@media (max-width: 767px) { .detail-header h1 { font-size: 26px; line-height: 36px; } .detail-summary { font-size: 17px; line-height: 30px; } .detail-header .user-inline-link { margin-left: 0; } }
</style>
