# 原型共享模块接口

这是 ITERATE r1 的原型开发接口说明。唯一交换主源为 [OpenAPI](../../contracts/openapi.json)，内存 adapter 到未来 HTTP 的映射见 [契约说明](../../contracts/README.md)。当前没有 HTTP 后端；UI 只读 `state`，修改经 `api`，不得分散 mock 结果。

`@shared/mock` 导出 Vue reactive `state: DemoState`、`api`、`setScenario(Scenario)`、`resetDemo()`、`resetRevision: Ref<number>`、`FIXED_NOW`、`TOPICS: string[]`、`notify(message)`、`toast: Ref<string>`、`formatDate(value)`、`statusLabel(value)`。

`FIXED_NOW = '2026-09-18T08:12:00+08:00'`。`resetDemo()` 清除模拟任务定时器、恢复 seed 并递增 resetRevision；Shell/表单借此重新挂载或同步，不能只监听 scenario（正常场景内也能重置）。`setScenario` 先重置再设置场景。localStorage 为每个 origin 的独立演示状态，两端不实时同步；不要把这个存储当作后端或用户权限系统。

除 `logout` 外 api 方法均异步，错误通过 throw Error；页面须 try/catch 保留输入。普通操作延迟约 350ms，采集/生成/评估通过额外定时器推进，error 场景写操作失败；重置使旧操作失效。

- `load(): Promise<void>`、`login(email, password): Promise<void>`、`register(email, password, name?): Promise<void>`、`logout(): void`。登录/注册仅修改演示身份；注册后进入首次订阅，密码校验至少 8 位。
- `savePreferences(Preferences): Promise<void>`、`saveDelivery(DeliverySettings): Promise<void>`。主题或关键词至少一类非空，保存增加偏好版本；时区/时间按固定时钟重算 nextRunAt，变更邮箱清除验证状态。
- `verifyEmail(): Promise<void>`、`testDelivery(): Promise<void>`、`deleteMemory(id): Promise<void>`
- `generateBrief(): Promise<string>` 返回 run ID，后续示例事件自动推进；`cancelRun(id): Promise<void>`
- `retryDelivery(id): Promise<void>`（id 可为 brief ID 或 delivery ID，保持原简报并增加尝试；邮件需启用并模拟验证）、`markRead(newsId): Promise<void>`（toggle 阅读状态，同 ID 一致赋值）。
- `saveSource(Source): Promise<void>`、`toggleSource(id): Promise<void>`、`fetchSource(id): Promise<void>`
- `saveModel(ModelConfig, key?: string): Promise<void>`（仅保存遮罩，不持久化 key）、`testModel(id): Promise<void>`、`toggleModel(id): Promise<void>`
- `saveConfig(AgentConfig): Promise<void>`、`publishConfig(id): Promise<void>`
- `runEvaluation(configVersion): Promise<string>`、`saveEvalCase(EvalCase): Promise<void>`
- `toggleUser(id): Promise<void>`

共享组件：

- `@shared/AppShell.vue`：prop `app="user"|"admin"`，default slot 放 router-view；内含导航、原型场景/重置、toast。
- `@shared/Badge.vue`：prop `status: string`，自动状态中文文本/色。
- `@shared/EmptyState.vue`：props `title`, `description?`, `error?`；default slot 放操作。
- `@shared/RunTimeline.vue`：props `run: AgentRun`, `technical?: boolean`，含事件/子任务。
- `@shared/Modal.vue`：props `open`, `title`，emit `close`；default slot 内容，footer slot 操作。

共享 CSS 在 main.ts `import '@shared/styles.css'`。可用 `.page-header`（h1+描述，右侧 actions）、`.eyebrow`、`.muted`、`.meta`、`.card`、`.stack`、`.row`、`.actions`、`.button`/`button--primary`/`button--ghost`、`.field-control`、`.field`、`.form-grid`、`.chip`/`.chip--active`、`.alert`/`alert--danger`/`alert--success`、`.table-wrap`、`.data-table`、`.tabs`、`.section-heading`、`.metric-grid`、`.metric`、`.mono`、`.empty-state`。页面可写 scoped CSS 布局，不重复定义色板。

Shell 管理全局 loading/error/unauthorized 页面；空场景由各页空数组/无主题处理，partial 场景通过相应数据状态呈现。应用默认演示已登录；登录页须可访问且标明模拟。所有数据为 synthetic，不使用真实凭据。
