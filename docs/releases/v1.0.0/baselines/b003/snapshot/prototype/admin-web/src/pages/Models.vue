<script setup lang="ts">
import { ref } from 'vue';
import { Plus, KeyRound, CheckCircle2, PlugZap } from 'lucide-vue-next';
import { state, api, notify } from '@shared/mock';
import type { ModelConfig } from '@shared/types';
import Badge from '@shared/Badge.vue';
import EmptyState from '@shared/EmptyState.vue';
import Modal from '@shared/Modal.vue';
const editing = ref(false); const key = ref(''); const busy = ref(''); const error = ref(''); const tested = ref('');
const blank = (): ModelConfig => ({ id: '', name: '', provider: 'OpenAI-compatible', modelId: '', endpoint: 'https://api.example.com/v1', keyMasked: '', role: '主模型', enabled: true, verified: false, contextWindow: 128000 });
const form = ref<ModelConfig>(blank());
function edit(model?: ModelConfig) { form.value = model ? { ...model } : blank(); key.value = ''; error.value = ''; editing.value = true; }
async function save() { busy.value = 'save'; error.value = ''; try { await api.saveModel({ ...form.value }, key.value || undefined); key.value = ''; editing.value = false; notify('模型配置已保存；请进行模拟连接测试。'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = ''; } }
async function test(id: string) { busy.value = id; error.value = ''; tested.value = ''; try { await api.testModel(id); tested.value = id; notify('模拟连接测试通过，未调用真实模型。'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = ''; } }
async function toggle(id: string) { busy.value = id; error.value = ''; try { await api.toggleModel(id); notify('模型启用状态已更新。'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = ''; } }
const roleName = (role: string) => role;
</script>
<template>
  <header class="page-header"><div><div class="eyebrow">MODEL REGISTRY</div><h1>模型与连接</h1><p class="muted">集中管理模型端点，让主 Agent、摘要与评估各司其职。</p></div><button class="button button--primary" @click="edit()"><Plus :size="16" />添加模型</button></header>
  <p v-if="error && !editing" class="alert alert--danger" role="alert">{{ error }}</p>
  <p class="alert"><KeyRound :size="17" />原型请使用演示密钥。只保留掩码，不存储密钥原文，也不进行真实鉴权。</p>
  <EmptyState v-if="!state.models.length" title="还没有可用模型" description="先添加模型端点与角色，再发布 Agent 配置。"><button class="button" @click="edit()">添加模型</button></EmptyState>
  <template v-else><p class="admin-scroll-hint">表格可左右滚动。</p><div class="table-wrap admin-section"><table class="data-table admin-table"><thead><tr><th>模型 / 提供商</th><th>用途</th><th>连接端点与密钥</th><th>连接状态</th><th>操作</th></tr></thead><tbody><tr v-for="model in state.models" :key="model.id"><td class="wide-cell"><strong>{{ model.name }}</strong><small class="mono">{{ model.modelId }}</small><small>{{ model.provider }} · {{ model.contextWindow.toLocaleString() }} Token</small></td><td class="nowrap">{{ roleName(model.role) }}</td><td class="wide-cell"><span class="mono">{{ model.endpoint }}</span><small class="mono">{{ model.keyMasked || '尚未配置密钥' }}</small></td><td><Badge :status="!model.enabled ? 'disabled' : model.verified ? 'healthy' : 'unverified'" /><small v-if="tested === model.id" class="row"><CheckCircle2 :size="13" />模拟测试通过</small></td><td><div class="actions"><button class="button button--ghost" :disabled="!!busy || !model.enabled" @click="test(model.id)"><PlugZap :size="15" />{{ busy === model.id ? '处理中…' : '测试' }}</button><button class="button button--ghost" @click="edit(model)">编辑</button><button class="button button--ghost" :disabled="!!busy" @click="toggle(model.id)">{{ model.enabled ? '停用' : '启用' }}</button></div></td></tr></tbody></table></div></template>
  <section class="card admin-section"><h2>配置如何生效</h2><p class="muted">模型注册表定义连接；Agent 配置版本引用具体模型。发布前需完成连接测试，已开始的运行保留原配置快照。</p><RouterLink to="/agent-configs">选择模型并调整 Agent 参数 →</RouterLink></section>
  <Modal :open="editing" :title="form.id ? '编辑模型连接' : '添加模型连接'" @close="editing = false; key = ''">
    <form id="model-form" class="admin-form stack" @submit.prevent="save">
      <p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p>
      <label class="field">显示名称<input v-model="form.name" class="field-control" maxlength="80" required placeholder="例如：日常简报主模型"></label>
      <div class="form-grid"><label class="field">提供商<select v-model="form.provider" class="field-control"><option value="OpenAI-compatible">OpenAI Compatible</option><option value="OpenAI">OpenAI</option><option value="Anthropic">Anthropic</option><option value="DeepSeek">DeepSeek</option></select></label><label class="field">模型用途<select v-model="form.role" class="field-control"><option value="主模型">主 Agent</option><option value="摘要模型">消息摘要</option><option value="评估模型">评估裁判</option><option value="子模型">子 Agent</option></select></label></div>
      <label class="field">模型 ID<input v-model="form.modelId" class="field-control mono" required placeholder="provider-model-id"></label>
      <label class="field">Base URL<input v-model="form.endpoint" class="field-control mono" type="url" required placeholder="https://api.example.com/v1"><span class="meta">仅支持 HTTPS 或本地开发端点，不在 URL 中填写凭据。</span></label>
      <label class="field">{{ form.id ? '替换 API Key（可选）' : '演示 API Key' }}<input v-model="key" class="field-control mono" type="password" autocomplete="new-password" :required="!form.id" placeholder="输入演示值，如 demo-key"><span class="meta">{{ form.id ? `现有引用 ${form.keyMasked || '未配置'}；留空保持不变。` : '原型不会持久化密钥原文。' }}</span></label>
      <label class="field">上下文容量（Token）<input v-model.number="form.contextWindow" class="field-control" type="number" min="4096" max="2000000" required></label>
    </form><template #footer><button class="button" :disabled="busy === 'save'" @click="editing = false; key = ''">取消</button><button class="button button--primary" form="model-form" type="submit" :disabled="busy === 'save'">{{ busy === 'save' ? '正在保存…' : '保存模型' }}</button></template>
  </Modal>
</template>
