# 原型共享开发接口（ITERATE r5）

唯一正式交换主源为 [OpenAPI](../../contracts/openapi.json)，映射见[契约说明](../../contracts/README.md)。当前Vue界面经集中 `mock.ts` 操作状态；`anonymous.ts` 调用开发专用 `/__demo` 服务。两者都不是正式FastAPI实现。静态dist/preview不含开发Cookie服务，匿名交互需运行用户Vite5173；管理监测还需管理员Vite5174代理。

## 用户状态与方法

`@shared/mock` 导出reactive `state: DemoState`、`api`、`anonymousEntry`、`setScenario`、`resetDemo`、`resetRevision`、`FIXED_NOW`、`TOPICS`、`notify`、`toast`、`formatDate`及`statusLabel`。

- `api.ensureAnonymousSession()` 自动创建/恢复服务器匿名Cookie会话；返回身份投影和当前公开生成，更新 `state.session`、`generation`、首次完成标记。请求合并，重试不盲目创建多个身份。`anonymousEntry` 提供busy/error/retryAt。
- `load()` 保留全局加载/失败场景。`savePreferences(Preferences)` 只接受version/role/topics/keywords，至少话题或关键词非空，背景最多500字、关键词20个且单项40字；保存后完成首次引导。`saveDelivery(DeliverySettings)` 只接受HH:mm时间，Asia/Shanghai每日站内发布。
- `generateBrief()` 创建公开生成并返回其ID，轮询更新 `state.generation: GenerationProgress | null`；完成后按保存的偏好快照生成模拟简报。`cancelGeneration()` 是服务能力；用户无运行详情页。
- `login(email,password)`、`logout()` 仅供管理员演示登录；用户页面不调用，原用户register和markRead已删除。
- `deleteMemory(id)` 为原型内部保留能力，不在用户设置展示。

`GenerationProgress`只有id/status/percent/remainingSeconds/updatedAt/briefId/error；模型、工具和事件不进入用户投影。新闻已删除read；共享内部Brief仍有runId/preferenceSnapshot，按管理AdminBrief校验，公开HTTP必须剔除这两项。用户组件不能读取内部运行字段。

原型偏好、示例简报和设置仍由浏览器按匿名账户隔离保存；身份、完成标记、生成状态、匿名统计及策略由本地开发服务维护。开发Cookie为HttpOnly/SameSite=Lax，HTTPS才加Secure；不使用document.cookie手写凭证。Cookie丢失产生新身份，403保留原身份提示不可用。生产还需完整数据库与资源归属校验。

## 开发HTTP边界

`anonymousApi` 包括session、touch、onboard、generate、progress、cancel；请求统一带凭据与JSON，`DemoHttpError`保存status和Retry-After。session返回 `{session,generation}` 仅是bootstrap封套，不是正式Session DTO。

`anonymousAdminApi` 包括login、session、logout、list、setStatus、savePolicy、simulateAbuse。list聚合users/events/policy供原型管理页；正式列表采用契约中的分页响应。`simulateAbuse`仅管理员演示按钮，不能部署为公开生产端点。

用户Vite5173挂载 `demo-server.ts`，管理员5174代理管理请求到同一服务，用独立管理员演示Cookie；监测可以观察到本地实际演示请求。匿名token只保存哈希，开发数据位于被Git忽略的 `.demo`。服务器重启/浏览器关闭与内存原型的语义不同，不能用浏览器定时器冒充真实后台Agent。

## 保留的管理模拟方法

`saveSource/toggleSource/fetchSource`、`saveModel/testModel/toggleModel`、`saveConfig/publishConfig`、`saveEvalCase/runEvaluation`、`cancelRun`、`retryDelivery`继续由集中adapter处理。模型只保留key遮罩；发布配置对后续运行生效；站内重试沿用原briefId，submitted仅表示已发布。

这些来源、模型、运行、实验和发布数据仍为synthetic。固定参考时钟 `2026-09-18T08:12:00+08:00`用于新闻seed；匿名HTTP活动使用实际服务器时间。场景/重置用于UI演示，不充当清除Cookie或绕过服务端配额的控制。

## 组件

管理员使用 `AppShell.vue` 与共享默认样式；用户独立使用 `ReaderShell.vue`、user-tokens.css和user.css。`Badge`、`EmptyState`、`Modal`等语义原语共用。`RunTimeline`只在管理端使用。

用户 `NewsArticle` 触发单条新闻详情，`NewsDetailDialog`管理对应内容和可访问弹窗；`GenerationProgress`组件只展示公开进度及估算，不渲染Agent事件。按钮、标签、状态色沿用双端design规范，任何跨端基础组件修改需验证两种主题。
