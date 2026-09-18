# 原型共享模块接口

这是 ITERATE r3 的原型开发接口说明。唯一交换主源为 [OpenAPI](../../contracts/openapi.json)，内存 adapter 到未来 HTTP 的映射见 [契约说明](../../contracts/README.md)。当前没有 HTTP 后端；UI 只读 `state`，修改经 `api`，不得分散 mock 结果。

`@shared/mock` 导出 Vue reactive `state: DemoState`、`api`、`setScenario(Scenario)`、`resetDemo()`、`resetRevision: Ref<number>`、`FIXED_NOW`、`TOPICS: string[]`、`notify(message)`、`toast: Ref<string>`、`formatDate(value)`、`statusLabel(value)`。

`FIXED_NOW = '2026-09-18T08:12:00+08:00'`。`resetDemo()` 清除模拟任务定时器、恢复 seed 并递增 resetRevision；Shell/表单借此重新挂载或同步，不能只监听 scenario（正常场景内也能重置）。`setScenario` 清除当前模拟任务并恢复其他示例数据，再设置场景；保留已保存偏好与 onboardingCompleted，不重新触发已完成的首次引导。`resetDemo` 则连同上述设置一起恢复 seed，并清空完成标记。localStorage 为每个 origin 的独立演示状态，两端不实时同步；不要把这个存储当作后端或用户权限系统。

除 `logout` 外 api 方法均异步，错误通过 throw Error；页面须 try/catch 保留输入。普通操作延迟约 350ms，采集/生成/评估通过额外定时器推进，error 场景写操作失败；重置使旧操作失效。

- `load(): Promise<void>`、`login(email, password): Promise<void>`、`register(email, password, name?): Promise<void>`、`logout(): void`。登录/注册仅修改演示身份；注册将 onboardingCompleted 重置为 false 并进入首次订阅，密码校验至少 8 位。
- `savePreferences(Preferences): Promise<void>`、`saveDelivery(DeliverySettings): Promise<void>`。Preferences 仅 version/role/topics/keywords，背景最长 500 字，关键词最多 20 个、每个最长 40 字；话题或关键词至少一类非空，保存增加版本并持久化 onboardingCompleted=true；DeliverySettings 仅 time，HH:mm 按 Asia/Shanghai 的每日站内计划解释，保存不立即生成。
- `deleteMemory(id): Promise<void>` 是共享服务能力，用户设置页不再提供记忆管理。邮箱验证与测试发送方法已移除。
- `generateBrief(): Promise<string>` 返回 run ID，后续示例事件自动推进；模拟筛选最近 24 小时、最多 10 条，命中任一所选话题或任一关键词即可入选，无匹配不凑数；背景只保存供正式 Agent 语义使用；`cancelRun(id): Promise<void>`
- `retryDelivery(id): Promise<void>`（id 可为 brief ID 或 delivery ID，保持原简报并增加尝试；仅 in_app 站内发布，submitted 表示已发布）、`markRead(newsId): Promise<void>`（toggle 阅读状态，同 ID 一致赋值）。
- `saveSource(Source): Promise<void>`、`toggleSource(id): Promise<void>`、`fetchSource(id): Promise<void>`
- `saveModel(ModelConfig, key?: string): Promise<void>`（仅保存遮罩，不持久化 key）、`testModel(id): Promise<void>`、`toggleModel(id): Promise<void>`
- `saveConfig(AgentConfig): Promise<void>`、`publishConfig(id): Promise<void>`
- `runEvaluation(configVersion): Promise<string>`、`saveEvalCase(EvalCase): Promise<void>`
- `toggleUser(id): Promise<void>`

共享组件：

- `@shared/AppShell.vue`：保留原侧栏控制台壳，当前由管理员项目使用；prop `app="user"|"admin"`，default slot 放 router-view。r2 用户端改用 `user-web/src/components/ReaderShell.vue` 和独立 `user-tokens.css`，两壳保留导航、原型场景/重置、toast。
- `@shared/Badge.vue`：prop `status: string`，自动状态中文文本/色。
- `@shared/EmptyState.vue`：props `title`, `description?`, `error?`；default slot 放操作。
- `@shared/RunTimeline.vue`：props `run: AgentRun`, `technical?: boolean`，含事件/子任务。
- `@shared/Modal.vue`：props `open`, `title`，emit `close`；default slot 内容，footer slot 操作。

共享 CSS 在 main.ts `import '@shared/styles.css'`。可用 `.page-header`（h1+描述，右侧 actions）、`.eyebrow`、`.muted`、`.meta`、`.card`、`.stack`、`.row`、`.actions`、`.button`/`button--primary`/`button--ghost`、`.field-control`、`.field`、`.form-grid`、`.chip`/`.chip--active`、`.alert`/`alert--danger`/`alert--success`、`.table-wrap`、`.data-table`、`.tabs`、`.section-heading`、`.metric-grid`、`.metric`、`.mono`、`.empty-state`。页面可写 scoped CSS 布局，不重复定义色板。

Shell 管理全局 loading/error/unauthorized 页面；空场景由各页空数组/无主题处理，partial 场景通过相应数据状态呈现。应用默认演示已登录；登录页须可访问且标明模拟。所有数据为 synthetic，不使用真实凭据。

首次演示 seed 的偏好为 version 0、背景空、话题和关键词空，onboardingCompleted=false；历史简报保留独立的示例快照。路由以身份与完成标记决定首次引导，不把现有历史简报或数组数量作为完成证据。有效保存后刷新和后续登录保留完成状态。
