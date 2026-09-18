<script setup lang="ts">
import { computed, ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import { Copy, Save, Rocket, ShieldCheck } from 'lucide-vue-next';
import { state, api, notify } from '@shared/mock';
import type { AgentConfig } from '@shared/types';
import Badge from '@shared/Badge.vue';
import EmptyState from '@shared/EmptyState.vue';
const selectedId = ref(state.configs.find(c => c.status === 'draft')?.id || state.configs[0]?.id || '');
const form = ref<AgentConfig | null>(state.configs.find(c => c.id === selectedId.value) ? structuredClone(JSON.parse(JSON.stringify(state.configs.find(c => c.id === selectedId.value)))) : null);
const error = ref(''); const busy = ref(''); const changed = ref(false);
onBeforeRouteLeave(() => !changed.value || window.confirm('当前 Agent 草稿尚未保存，确认离开并放弃修改？'));
const tools = ['list_dir', 'read_file', 'search_content', 'write_file', 'bash', 'web_search'];
const published = computed(() => state.configs.filter(c => c.status === 'published').at(-1));
const locked = computed(() => form.value?.status === 'published');
const models = computed(() => state.models.filter(m => m.enabled && m.verified));
const diff = computed(() => {
  if (!form.value || !published.value) return '暂无已发布版本可比较。';
  const names: Record<string, string> = { maxModelCalls: '模型调用上限', maxToolCalls: '工具调用上限', maxSeconds: '运行超时', summaryTokens: '摘要 Token 阈值', summaryMessages: '摘要消息阈值', summaryRatio: '容量触发比例', subagentConcurrency: '子 Agent 并发', modelId: '主模型引用', summaryModelId: '摘要模型引用', systemPrompt: '系统提示词', tools: '工具列表' };
  return Object.entries(names).filter(([key]) => JSON.stringify((form.value as any)[key]) !== JSON.stringify((published.value as any)[key])).map(([key, label]) => `${label}: ${JSON.stringify((published.value as any)[key])}\n      → ${JSON.stringify((form.value as any)[key])}`).join('\n\n') || '当前参数与已发布版本相同。';
});
function choose(config: AgentConfig) { if (changed.value && !window.confirm('当前草稿尚未保存，放弃修改并切换版本？')) return; selectedId.value = config.id; form.value = JSON.parse(JSON.stringify(config)); changed.value = false; error.value = ''; }
function clone() {
  if (changed.value && !window.confirm('当前草稿尚未保存，放弃修改并新建版本？')) return;
  const source = form.value || published.value;
  const version = `v${Math.max(0, ...state.configs.map(c => Number(c.version.replace(/\D/g, '')) || 0)) + 1}`;
  form.value = source ? { ...JSON.parse(JSON.stringify(source)), id: '', version, status: 'draft' } : { id: '', name: '每日新闻编辑', version, status: 'draft', modelId: models.value[0]?.id || '', summaryModelId: models.value[0]?.id || '', maxModelCalls: 30, maxToolCalls: 60, maxSeconds: 480, summaryTokens: 24000, summaryMessages: 40, summaryRatio: 0.65, subagentConcurrency: 2, tools: [...tools], systemPrompt: '' };
  selectedId.value = ''; changed.value = true; error.value = '';
}
async function save() { if (!form.value) return; busy.value = 'save'; error.value = ''; try { await api.saveConfig({ ...form.value, tools: [...form.value.tools] }); const saved = state.configs.find(c => c.version === form.value?.version); if (saved) { form.value = JSON.parse(JSON.stringify(saved)); selectedId.value = saved.id; } changed.value = false; notify('Agent 草稿已保存，发布后对新运行生效。'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = ''; } }
async function publish() { if (!form.value?.id || changed.value) return; busy.value = 'publish'; error.value = ''; try { await api.publishConfig(form.value.id); form.value.status = 'published'; notify(`配置 ${form.value.version} 已发布，仅新运行使用此版本。`); } catch (e) { error.value = (e as Error).message; } finally { busy.value = ''; } }
</script>
<template>
  <header class="page-header"><div><div class="eyebrow">AGENT CONFIGURATION</div><h1>Agent 配置</h1><p class="muted">用版本记录每次调优，让运行结果有据可查。</p></div><button class="button" @click="clone"><Copy :size="16" />{{ form ? '复制为新草稿' : '新建配置草稿' }}</button></header>
  <div class="admin-config-layout"><aside class="admin-config-list" aria-label="配置版本"><button v-for="config in state.configs" :key="config.id" class="button admin-config-choice" :aria-pressed="selectedId === config.id" @click="choose(config)"><span><strong>{{ config.version }}</strong><small>{{ config.name }}</small></span><Badge :status="config.status" /></button></aside>
    <div v-if="form" class="stack">
      <p v-if="locked" class="alert"><ShieldCheck :size="17" />已发布版本只读。复制为新草稿后修改，历史运行保留原参数。</p>
      <p v-if="!models.length" class="alert alert--danger">没有通过连接测试的启用模型。请先到<RouterLink to="/models">模型与连接</RouterLink>完成配置。</p>
      <form class="card admin-form stack" @submit.prevent="save" @input="changed = true" @change="changed = true">
        <div class="section-heading"><h2>{{ form.version }} · {{ locked ? '已发布配置' : '编辑草稿' }}</h2><Badge :status="form.status" /></div>
        <p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p>
        <fieldset :disabled="locked || !!busy"><legend>模型与角色</legend><div class="stack"><label class="field">配置名称<input v-model="form.name" class="field-control" required maxlength="80"></label><div class="form-grid"><label class="field">主 Agent 模型<select v-model="form.modelId" class="field-control" required><option value="" disabled>选择可用模型</option><option v-for="model in models" :key="model.id" :value="model.id">{{ model.name }}</option></select></label><label class="field">摘要模型<select v-model="form.summaryModelId" class="field-control" required><option value="" disabled>选择可用模型</option><option v-for="model in models" :key="model.id" :value="model.id">{{ model.name }}</option></select></label></div></div></fieldset>
        <fieldset :disabled="locked || !!busy"><legend>运行预算</legend><div class="form-grid"><label class="field">最多模型调用<input v-model.number="form.maxModelCalls" class="field-control" type="number" min="1" max="100" required></label><label class="field">最多工具调用<input v-model.number="form.maxToolCalls" class="field-control" type="number" min="1" max="200" required></label><label class="field">运行超时（秒）<input v-model.number="form.maxSeconds" class="field-control" type="number" min="30" max="3600" required></label><label class="field">子 Agent 最大并发<input v-model.number="form.subagentConcurrency" class="field-control" type="number" min="0" max="5" required><span class="meta">0 表示停用子 Agent；子任务共享主任务预算。</span></label></div></fieldset>
        <fieldset :disabled="locked || !!busy"><legend>上下文摘要</legend><div class="form-grid"><label class="field">累计 Token 阈值<input v-model.number="form.summaryTokens" class="field-control" type="number" min="1000" max="1000000" required></label><label class="field">消息数量阈值<input v-model.number="form.summaryMessages" class="field-control" type="number" min="5" max="200" required></label><label class="field">上下文容量触发比例<input v-model.number="form.summaryRatio" class="field-control" type="number" min="0.1" max="0.9" step="0.05" required><span class="meta">0.65 表示 65%；达到任一阈值触发压缩。</span></label></div><p class="admin-note">预算包含现有摘要。最近用户原始输入保留；摘要写入独立字段，由渲染中间件注入上下文。</p></fieldset>
        <fieldset :disabled="locked || !!busy"><legend>允许的工具</legend><div class="admin-checks"><label v-for="tool in tools" :key="tool"><input v-model="form.tools" type="checkbox" :value="tool"><span class="mono">{{ tool }}</span></label></div><p class="admin-note">文件路径通过沙箱映射；bash 的进程隔离与只读挂载由 Harness 强制执行。</p></fieldset>
        <fieldset :disabled="locked || !!busy"><legend>系统提示词</legend><label class="field">编辑规则<textarea v-model="form.systemPrompt" class="field-control" rows="7" required maxlength="12000" placeholder="说明筛选偏好、引用规则、去重和失败时行为。"></textarea></label></fieldset>
        <details class="admin-diff"><summary>与已发布 {{ published?.version || '版本' }} 的差异</summary><pre>{{ diff }}</pre></details>
        <div v-if="!locked" class="actions"><button class="button button--primary" type="submit" :disabled="!!busy"><Save :size="16" />{{ busy === 'save' ? '正在保存…' : '保存草稿' }}</button><button class="button" type="button" :disabled="!!busy || changed || !form.id" @click="publish"><Rocket :size="16" />{{ busy === 'publish' ? '正在发布…' : '发布此版本' }}</button><span class="meta">{{ changed ? '有未保存修改，请先保存草稿' : '发布后仅对新运行生效' }}</span></div>
      </form>
    </div><EmptyState v-else title="还没有 Agent 配置" description="创建草稿，选择模型并设置工具与运行预算。"><button class="button button--primary" @click="clone">新建配置草稿</button></EmptyState>
  </div>
</template>
