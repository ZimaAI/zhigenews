import { reactive, ref, watch } from 'vue';
import { createSeed, EXAMPLE_EVENTS, FIXED_NOW, TOPICS } from './fixtures';
import type { AgentConfig, AgentRun, Brief, DeliverySettings, DemoState, EvalCase, ModelConfig, Preferences, Scenario, Source } from './types';
export { FIXED_NOW, TOPICS };
const STORAGE = 'zhigenews-prototype-r1.1';
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
function initialState(): DemoState {
  try {
    const data = JSON.parse(localStorage.getItem(STORAGE) || 'null');
    if (data?.preferences && Array.isArray(data?.briefs) && data?.sources) {
      // A reloaded prototype cannot pretend its in-memory timers still run.
      for (const run of data.runs) if (['running', 'queued', 'cancelling'].includes(run.status)) run.status = 'cancelled';
      return { ...createSeed(), ...data, scenario: 'normal', loaded: true };
    }
  } catch { /* A resettable demo does not require browser storage. */ }
  return createSeed();
}
export const state = reactive<DemoState>(initialState());
export const toast = ref('');
export const resetRevision = ref(0);
let toastTimer: ReturnType<typeof setTimeout>;
let epoch = 0;
const timers = new Set<ReturnType<typeof setTimeout>>();
watch(state, () => { try { localStorage.setItem(STORAGE, JSON.stringify(state)); } catch { /* private browsing */ } }, { deep: true });
export function notify(message: string) { toast.value = message; clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.value = '', 6000); }
function schedule(callback: () => void, delay: number) { const timer = setTimeout(() => { timers.delete(timer); callback(); }, delay); timers.add(timer); }
const sleep = (ms = 350) => new Promise<void>(resolve => setTimeout(resolve, ms));
function id(prefix: string) { return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`; }
async function guard() {
  const currentEpoch = epoch;
  await sleep();
  if (currentEpoch !== epoch) throw new Error('示例已重置，请重新操作。');
  if (state.scenario === 'error') throw new Error('模拟服务暂不可用，输入已保留。请切回正常场景后重试。');
  if (state.scenario === 'unauthorized') throw new Error('模拟权限校验失败：当前身份不能执行此操作。');
}
function get<T extends { id: string }>(items: T[], key: string): T { const value = items.find(x => x.id === key); if (!value) throw new Error('示例记录不存在，请返回列表。'); return value; }
export function resetDemo() {
  epoch++; for (const timer of timers) clearTimeout(timer); timers.clear();
  Object.assign(state, createSeed()); resetRevision.value++; notify('已恢复初始示例，时钟回到 2026-09-18 08:12。');
}
export function setScenario(scenario: Scenario) {
  resetDemo(); state.scenario = scenario;
  if (scenario === 'loading') { state.loaded = false; schedule(() => state.loaded = true, 1800); }
  if (scenario === 'empty') {
    state.briefs = []; state.runs = []; state.sources = []; state.models = []; state.configs = []; state.evaluations = []; state.evalCases = []; state.users = []; state.deliveries = []; state.memories = [];
    state.preferences.topics = []; state.preferences.keywords = [];
  }
  if (scenario === 'partial') { state.briefs[0]!.generationStatus = 'partial'; state.runs[0]!.status = 'partial'; }
  notify(`已切换为${{ normal: '正常', loading: '加载', empty: '空内容', error: '请求失败', partial: '部分完成', unauthorized: '无权限' }[scenario]}示例。`);
}
export function formatDate(value: string | null | undefined) {
  if (!value) return '未知';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: state.delivery.timezone || 'Asia/Shanghai' }).format(date);
}
export function statusLabel(status: string) {
  return ({ completed: '已完成', running: '运行中', queued: '排队中', partial: '部分完成', failed: '失败', cancelling: '正在取消', cancelled: '已取消', pending: '待提交', submitted: '已提交发送', disabled: '已停用', unknown: '状态未知', healthy: '正常', syncing: '同步中', unverified: '待验证', published: '已发布', draft: '草稿', active: '正常', verified: '已验证', success: '成功' } as Record<string, string>)[status] || status;
}
function nextRun(setting: DeliverySettings): string {
  if (!setting.dailyEnabled) return '已暂停 · 恢复后安排下一次，不补发历史';
  // Use the deterministic demo instant, then find the next matching local minute.
  const formatter = new Intl.DateTimeFormat('sv-SE', { timeZone: setting.timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
  const start = new Date(FIXED_NOW).getTime();
  for (let minute = 1; minute <= 60 * 49; minute++) {
    const text = formatter.format(new Date(start + minute * 60000));
    if (text.slice(-5) === setting.time) return `${text} · ${setting.timezone}`;
  }
  return `下一个有效的 ${setting.time} · ${setting.timezone}（模拟）`;
}
function emailValid(value: string) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value); }

export const api = {
  async load() { state.loaded = false; try { await guard(); } finally { state.loaded = true; } },
  async login(email: string, password: string) { await guard(); if (!emailValid(email) || password.length < 8) throw new Error('请输入有效邮箱和至少 8 位演示密码。'); state.authenticated = true; notify('已进入演示账户，不执行真实身份认证。'); },
  async register(email: string, password: string, name?: string) { await this.login(email, password); state.preferences.topics = []; state.preferences.keywords = []; state.briefs = []; if (!state.users.length) state.users.push({ id: 'user-demo', name: name?.trim() || '新读者', email, role: 'user', status: 'active', topics: [] }); else { state.users[0]!.email = email; if (name?.trim()) state.users[0]!.name = name.trim(); } notify('演示账户已创建，请完成首次订阅。'); },
  logout() { state.authenticated = false; },
  async savePreferences(value: Preferences) {
    await guard(); if (!value.topics.length && !value.keywords.length) throw new Error('至少选择一个主题或添加一个关键词。');
    if (value.maxItems < 1 || value.maxItems > 30 || value.windowHours < 1 || value.windowHours > 168) throw new Error('条数范围为 1–30，时间窗口为 1–168 小时。');
    const clean = (xs: string[]) => [...new Set(xs.map(x => x.trim()).filter(Boolean))];
    state.preferences = { ...clone(value), topics: clean(value.topics), keywords: clean(value.keywords), excludedKeywords: clean(value.excludedKeywords), version: state.preferences.version + 1 };
    notify('订阅已保存，下次生成将使用新偏好。');
  },
  async saveDelivery(value: DeliverySettings) {
    await guard(); if (value.emailEnabled && !emailValid(value.email)) throw new Error('请输入有效的收件邮箱。');
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value.time)) throw new Error('请选择有效的每日推送时间。');
    const verified = value.email === state.delivery.email ? state.delivery.verified : false;
    state.delivery = { ...clone(value), verified, nextRunAt: nextRun(value) };
    notify('推送设置已保存（模拟），没有发送邮件。');
  },
  async verifyEmail() { await guard(); if (!emailValid(state.delivery.email)) throw new Error('请先保存有效邮箱。'); state.delivery.verified = true; notify('邮箱验证演示完成，没有真实验证邮件。'); },
  async testDelivery() {
    await guard(); if (!state.delivery.emailEnabled || !state.delivery.verified) throw new Error('请先启用邮件、保存地址并完成模拟验证。');
    state.deliveries.unshift({ id: id('test'), briefId: '', userName: '林序', destination: state.delivery.email.replace(/^(.).+@/, '$1•••@'), channel: 'email', status: 'submitted', attempts: 1, time: FIXED_NOW, error: '' });
    notify('模拟测试已提交发送；没有向外部邮箱发送消息。');
  },
  async deleteMemory(key: string) { await guard(); state.memories = state.memories.filter(x => x.id !== key); notify('这条示例记忆已清理。'); },
  async generateBrief() {
    const existing = state.runs.find(x => ['queued', 'running', 'cancelling'].includes(x.status)); if (existing) return existing.id;
    await guard();
    const raced = state.runs.find(x => ['queued', 'running', 'cancelling'].includes(x.status)); if (raced) return raced.id;
    if (!state.preferences.topics.length && !state.preferences.keywords.length) throw new Error('请先设置关注主题或关键词。');
    const prefs = clone(state.preferences); const seed = createSeed(); const runId = id('run'); const activeConfig = [...state.configs].reverse().find(x => x.status === 'published');
    const run: AgentRun = { ...clone(seed.runs[0]!), id: runId, userName: state.users[0]?.name || '林序', status: 'running', configVersion: activeConfig?.version || 'v3', startedAt: FIXED_NOW, events: [], subtasks: [], elapsedSeconds: 0, inputTokens: 0, outputTokens: 0, cost: 0, searchCount: 0 };
    state.runs.unshift(run);
    EXAMPLE_EVENTS.forEach((event, index) => schedule(() => {
      const current = state.runs.find(x => x.id === runId); if (!current || current.status !== 'running') return;
      const eventTime = new Intl.DateTimeFormat('en-GB', { timeZone: state.delivery.timezone, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(new Date(FIXED_NOW).getTime() + index * 1000));
      current.events.push({ ...clone(event), time: eventTime }); current.elapsedSeconds = index + 1;
      if (index !== EXAMPLE_EVENTS.length - 1) return;
      current.status = state.scenario === 'partial' ? 'partial' : 'completed'; current.inputTokens = 12640; current.outputTokens = 2180; current.cost = 0.086; current.searchCount = 2; current.subtasks = clone(seed.runs[0]!.subtasks);
      const items = clone(seed.briefs[0]!.items).filter(item => {
        const text = `${item.title} ${item.summary}`.normalize('NFKC').toLowerCase();
        return !!item.publishedAt && new Date(item.publishedAt).getTime() >= new Date(FIXED_NOW).getTime() - prefs.windowHours * 3600000 && !prefs.excludedKeywords.some(k => text.includes(k.toLowerCase())) && prefs.sourceTypes.includes(item.sourceType) &&
          (prefs.keywordMode !== 'required' || !prefs.keywords.length || prefs.keywords.some(k => text.includes(k.toLowerCase()))) &&
          (!prefs.topics.length || prefs.topics.includes(item.topic));
      }).slice(0, prefs.maxItems);
      current.events[current.events.length - 1]!.detail = `${items.length} 条示例内容已保存。投递结果单独记录。`;
      for (const item of items) item.read = state.briefs.flatMap(x => x.items).find(x => x.id === item.id)?.read || false;
      const completedAt = new Date(new Date(FIXED_NOW).getTime() + index * 1000).toISOString();
      const brief: Brief = { ...clone(seed.briefs[0]!), id: id('brief'), date: '2026-09-18', version: state.briefs.filter(x => x.date === '2026-09-18').length + 1, runId, items, summary: items.length ? `根据本次订阅，从固定示例资料中整理出 ${items.length} 条阅读线索，每条保留推荐理由与参考入口。以下为交互演示内容，不是当天真实新闻。` : '固定示例资料中没有符合当前订阅条件的内容。可以调整订阅后重新生成，系统不会自动放宽筛选条件。', generationStatus: current.status, preferenceSnapshot: prefs, generatedAt: completedAt, deliveryStatus: state.delivery.emailEnabled ? 'pending' : 'disabled' };
      state.briefs.unshift(brief);
      if (state.delivery.emailEnabled) {
        const enabled = state.delivery.verified; brief.deliveryStatus = enabled ? 'submitted' : 'failed'; state.briefs[0]!.deliveryStatus = brief.deliveryStatus;
        state.deliveries.unshift({ id: id('delivery'), briefId: brief.id, userName: run.userName, destination: state.delivery.email.replace(/^(.).+@/, '$1•••@'), channel: 'email', status: brief.deliveryStatus, attempts: 1, time: FIXED_NOW, error: enabled ? '' : '收件地址尚未完成模拟验证。' });
      }
      notify(items.length ? `已生成 ${items.length} 条示例内容，未执行真实模型或邮件。` : '未找到匹配的示例内容，没有自动放宽订阅条件。');
    }, 1200 * (index + 1)));
    return runId;
  },
  async cancelRun(key: string) { const run = get(state.runs, key); if (!['running', 'queued'].includes(run.status)) return; const previous = run.status; run.status = 'cancelling'; try { await guard(); } catch (error) { run.status = previous; throw error; } run.status = 'cancelled'; run.events.push({ id: run.events.length + 1, time: '08:12:00', title: '运行已取消', detail: '示例任务已停止，已有简报仍可阅读。', status: 'cancelled', duration: '' }); notify('示例运行已取消。'); },
  async retryDelivery(key: string) {
    await guard(); const delivery = state.deliveries.find(x => x.id === key || x.briefId === key); if (!delivery) throw new Error('找不到投递记录。');
    if (!['failed', 'unknown'].includes(delivery.status)) throw new Error('只有失败或状态未知的记录需要重试。');
    if (delivery.channel === 'email' && (!state.delivery.emailEnabled || !state.delivery.verified)) throw new Error('请先启用邮件并完成收件地址的模拟验证，再重试投递。');
    delivery.attempts++; delivery.status = 'submitted'; delivery.error = ''; const brief = state.briefs.find(x => x.id === delivery.briefId); if (brief) brief.deliveryStatus = 'submitted'; notify('同一份简报已模拟重新提交，尚无送达回执。');
  },
  async markRead(key: string) { await guard(); const first = state.briefs.flatMap(x => x.items).find(x => x.id === key); if (!first) return; const next = !first.read; for (const brief of state.briefs) for (const item of brief.items) if (item.id === key) item.read = next; },
  async saveSource(value: Source) { await guard(); if (!value.name.trim() || !/^https?:\/\//.test(value.url)) throw new Error('请填写来源名称与 HTTP(S) 地址。'); if (value.interval < Math.max(60, value.upstreamInterval)) throw new Error('轮询间隔不能低于上游更新间隔，且至少 60 秒。'); const old = state.sources.find(x => x.id === value.id); if (old) { const changed = old.url !== value.url || old.kind !== value.kind || old.sourceId !== value.sourceId; Object.assign(old, clone(value), changed ? { status: 'unverified' } : {}); } else state.sources.unshift({ ...clone(value), id: id('src'), status: 'unverified' }); notify('来源配置已保存（模拟）。'); },
  async toggleSource(key: string) { await guard(); const source = get(state.sources, key); source.status = source.status === 'disabled' ? 'unverified' : 'disabled'; source.nextFetch = source.status === 'disabled' ? '' : FIXED_NOW; notify(source.status === 'disabled' ? '来源已停用，保留历史快照。' : '来源已启用，等待模拟验证。'); },
  async fetchSource(key: string) { await guard(); const source = get(state.sources, key); if (source.status === 'disabled') throw new Error('请先启用来源。'); source.status = 'syncing'; await sleep(700); if (!state.sources.includes(source)) return; source.status = source.url.includes('36kr') ? 'failed' : 'healthy'; source.error = source.status === 'failed' ? '示例响应为 HTML，解析失败，保留旧快照。' : ''; if (source.status === 'healthy') { source.lastSuccess = FIXED_NOW; source.nextFetch = new Date(new Date(FIXED_NOW).getTime() + source.interval * 1000).toISOString(); source.items = source.items || 12; } notify(source.status === 'healthy' ? '模拟同步完成。' : '模拟同步失败：响应不是 RSS。'); },
  async saveModel(value: ModelConfig, key?: string) { await guard(); if (!value.name.trim() || !value.modelId.trim() || !/^https?:\/\//.test(value.endpoint)) throw new Error('请填写名称、模型 ID 和 HTTP(S) 端点。'); const saved = { ...clone(value), keyMasked: key ? `demo-key-••••${key.slice(-4)}` : value.keyMasked, verified: false }; const old = state.models.find(x => x.id === value.id); if (old) Object.assign(old, saved); else state.models.unshift({ ...saved, id: id('model') }); notify('模型配置已保存，密钥原文不会保存在原型中。'); },
  async testModel(key: string) { await guard(); const model = get(state.models, key); if (!model.keyMasked) throw new Error('请先设置一个演示密钥。'); model.verified = true; notify('模拟连接测试通过，未向端点发出请求。'); },
  async toggleModel(key: string) { await guard(); const model = get(state.models, key); model.enabled = !model.enabled; },
  async saveConfig(value: AgentConfig) { await guard(); if (!value.name.trim() || !value.version.trim() || !value.systemPrompt.trim() || value.maxModelCalls < 1 || value.maxToolCalls < 1 || value.summaryRatio <= 0 || value.summaryRatio >= 1) throw new Error('请填写名称/提示词，并检查调用预算与摘要阈值。'); const old = state.configs.find(x => x.id === value.id); if (old?.status === 'published') throw new Error('已发布版本只读，请复制为新草稿。'); if (state.configs.some(x => x.version === value.version && x.id !== value.id)) throw new Error('版本号已存在，请使用新版本。'); if (old) Object.assign(old, clone(value), { status: 'draft' }); else state.configs.push({ ...clone(value), id: id('config'), status: 'draft' }); notify('配置草稿已保存，已发布版本保持不变。'); },
  async publishConfig(key: string) { await guard(); const config = get(state.configs, key); if (![config.modelId, config.summaryModelId].every(id => state.models.some(x => x.id === id && x.enabled && x.verified))) throw new Error('主模型与摘要模型均需启用并完成模拟连接测试。'); config.status = 'published'; notify(`${config.version} 已发布，仅影响后续示例运行。`); },
  async runEvaluation(configVersion: string) { await guard(); if (!state.evalCases.length) throw new Error('请先添加评估样例。'); if (!state.models.some(x => x.role === '评估模型' && x.enabled && x.verified)) throw new Error('请先启用评估模型并完成模拟连接测试。'); if (!state.configs.some(x => x.version === configVersion)) throw new Error('配置版本不存在。'); const evaluation = { id: id('eval'), name: `${configVersion} · 新实验`, configVersion, status: 'running', relevance: null, faithfulness: null, citations: null, cost: null, latency: null, cases: state.evalCases.length, createdAt: FIXED_NOW }; state.evaluations.unshift(evaluation); schedule(() => { const current = state.evaluations.find(x => x.id === evaluation.id); if (current) Object.assign(current, { status: 'completed', relevance: 4.3, faithfulness: 4.4, citations: 100, cost: 0.18, latency: 11.6 }); notify('模拟评估完成；分数为固定演示数据。'); }, 1800); return evaluation.id; },
  async saveEvalCase(value: EvalCase) { await guard(); if (!value.name.trim() || !value.preference.trim() || !value.expected.trim()) throw new Error('请填写名称、偏好与预期行为。'); const old = state.evalCases.find(x => x.id === value.id); if (old) Object.assign(old, clone(value)); else state.evalCases.push({ ...clone(value), id: id('case') }); notify('固定评估样例已保存。'); },
  async toggleUser(key: string) { await guard(); const user = get(state.users, key); user.status = user.status === 'active' ? 'disabled' : 'active'; notify('用户状态已模拟更新。'); },
};
