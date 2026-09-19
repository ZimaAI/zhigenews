# v1.0.0 交换契约

本草稿的交换契约为 [openapi.json](openapi.json)，OpenAPI 3.1 / JSON Schema 2020-12；当前50 schemas、51操作、22个synthetic固定样例。本规范将已批准 r5 行为细化为正式 HTTP 边界，冻结身份以工作流基线快照为准。正式运行与客户端类型生成使用 `backend/src/zhigenews/contracts/openapi.json`。原型 `/__demo` 是独立的开发服务命名空间，不能当作正式API；契约验证不等于后端实现通过。

2026-09-19 用户要求移除现有长期记忆机制，后续另行设计实现。当前草稿与运行契约均已删除长期记忆列表/删除接口及 `Memory`、`MemoryPage`；历史冻结基线仅供追溯，不代表当前支持这些能力。线程 checkpoint、会话摘要和显式订阅偏好继续保留。

## 交换与内部模型

用户响应为 `Session`、`Preferences`、`DeliverySettings`、`NewsItem`、`Brief`、`GenerationProgress`。Session只含kind=anonymous、userId、name、onboardingCompleted，不返回token；Cookie由服务器签发。`NewsItem.read`已删除。公开Brief不含runId和preferenceSnapshot，技术关联保留在内部/管理 `AdminBrief`。`AgentRun`、RunEvent、Subtask只供管理员，不能直接序列化为用户响应。

原型shared/types.ts中的Brief目前是内部聚合模型，映射AdminBrief；正式用户客户端必须从公开Brief生成。DemoState、Scenario、选中新闻、toast、筛选和表单草稿属于页面状态。响应/写请求分开，禁止把完整页面state写回Gateway。

`GenerationProgress`只有id、status、percent、remainingSeconds、updatedAt、briefId、error。percent为0–100或null，remainingSeconds为非负整数或null；未知估计不表示0秒。发布前不能报100%/completed，时间可随负载调整。不得混入模型、事件、工具、子任务、配置或工作区。

固定样例封套为 `{synthetic:true,schema,data}`，仅按对应schema验证data；固定内容与参考链接不证明当天真实新闻。来源rss/newsnow/search、Source周期单位秒、评估0–5与引用0–100%等规则保留。类型和seed不是另一份权威契约。

## 路由

所有正式路由前缀 `/api/v1`；列表响应 `{items,nextCursor}`，本表省略前缀。

| 操作 | 路由 | 边界 |
| --- | --- | --- |
| 自动匿名进入 | POST /auth/anonymous | 无有效Cookie且通过IP门槛时建号/Set-Cookie；有Cookie幂等恢复；封禁403不换号 |
| 恢复会话 | GET /auth/session | Session，不建号；缺失/过期401 |
| 管理员会话 | POST /admin/auth/login，GET/DELETE /admin/auth/session | 独立Cookie和AdminSession，用户匿名身份不提升权限 |
| 偏好 | GET/PUT /me/preferences | version与话题/背景/关键词；成功原子完成引导，冲突409 |
| 推送时间 | GET/PUT /me/delivery-settings | 只有time，每日站内、系统时区Asia/Shanghai |
| 简报 | GET/POST /me/briefs，GET /me/briefs/{id} | 创建202返回公开GenerationProgress；阅读返回公开Brief |
| 生成进度 | GET /me/generations/{id} | 仅本人公开进度，不返回运行事件 |
| 恢复当前生成 | GET /me/generations/current | 仅凭Cookie恢复最近一次本人生成（含终态）；尚无生成时返回null |
| 取消生成 | POST /me/generations/{id}/cancel | 服务能力；先cancelling，由worker确认cancelled，不改变每日计划 |
| 本人发布服务 | /me/deliveries | 发布重试不重新生成 |
| 来源/模型/配置/评估/发布 | /admin/sources、models、agent-configs、evaluations、deliveries等 | 保持既有管理契约；key只写不回显 |
| 管理运行 | /admin/runs、/{id}、/{id}/cancel、/{id}/events | 管理员检查、SSE回放，普通用户不可访问 |
| 匿名监测 | GET /admin/anonymous-accounts，PUT /{id}/status | 脱敏监测，active/blocked和1–200字原因；管理审计 |
| 风险事件/策略 | GET /admin/abuse-events，GET/PUT /admin/anonymous-policy | 真实统计与限流，策略整数范围见schema |

已删除用户注册/密码登录写接口、`/me/news/{id}/read`及全部`/me/runs*`。旧管理/users转换为匿名监测接口。旧用户页面链接可重定向，但不保留泄露运行过程的HTTP兼容接口。契约未发布，无生产旧客户端迁移；历史要求见spec/07-changes.md。

`GET /me/briefs` 支持 `q/date/topic/status/cursor/limit`；q搜索简报标题、摘要和新闻标题，先合并筛选再分页。所有列表默认20条、最多100条；nextCursor为空表示没有下一页。静态路径 `/me/generations/current` 必须先于 `{id}` 路径匹配。

## 身份、滥用与错误

服务器生成不透明token，仅Set-Cookie传递，生产HttpOnly/Secure/SameSite=Lax/Path=/；保存哈希并执行过期和撤销。同Cookie保持个人偏好、历史和完成标记；Cookie丢失形成新身份，无密码恢复路径。被封禁会话403不自动换号；匿名用户拥有全部用户端功能，但所有管理路由使用独立adminSessionCookie。跨账号资源404，客户端userId声明不作为授权依据。

写操作检查允许的Origin和CSRF（JSON/专用头或服务端token），SameSite不单独承担CSRF保护；配置明确的凭据CORS源。具体依据和生产/开发差异见[架构](../spec/04-architecture.md)。

错误统一 `{code,message,requestId,fields?}`。400输入错误、401会话失效、403角色/ACCOUNT_BLOCKED/CSRF_REJECTED、404不可见、409版本/幂等冲突、429配额、503依赖不可用。429必须返回Retry-After秒数，前端停止立即重试。

账号每分钟请求、每日生成与并发，另有同IP新账号速率；默认60、20、1、10，范围分别1–600、1–100、1–10、1–100。服务器原子判定并入队，重复幂等请求不重复扣配额；封禁停止新生成/后续调度，解封不重置限制。清Cookie不重置IP桶。监测只含脱敏IP标签、计数、风险与原因，禁止token/原始IP泄漏；封禁、解封及策略修改记录管理员审计。

创建生成、发布重试、采集、实验使用Idempotency-Key；同身份/路由/key/body返回原操作，同key不同body409。SSE只在管理域，Last-Event-ID不是权限凭证。

## 正式证据与评估字段

NewsItem必须返回实际`fetchedAt`和不透明`snapshotId`；publishedAt未知保持null，不能以抓取时间补齐。公开Brief用`missingSources`列出缺失来源，不泄露内部运行标识。Source返回当前快照标识/采集时刻、最近HTTP尝试时刻、缓存年龄、stale与上游配置版本。失败与304保留原快照；304可以延长有效性，不能将旧数据伪装为新采集内容。

RunEvent.time为完整RFC 3339时间，页面自行格式化；AgentRun.inputTokens/outputTokens/cost未知为null。真实提供商没有返回usage或未配置价格时，不能补0充当已测量值。SSE仍以单个run内的事件序号作为Last-Event-ID。

EvalCase的preferenceSnapshot、fixedAt、sourceSnapshotIds和revision组成固定输入。保留原三字段编辑；创建省略可选固定字段时服务器捕获当时可用来源快照和时钟，将偏好描述存为背景（version=0、topics/keywords为空）。编辑省略固定字段保持原值。显式空快照数组表示无证据用例，不允许运行时自动改用实时搜索。每次保存递增revision。

创建实验原子绑定全部当前用例修订、模型/配置、datasetVersion与scorerVersion；空用例集拒绝执行。Evaluation.results给出逐用例结果，scores明确metric、rule/human/llm方法、value、maximum、passed与失败原因。未执行或失败的评分为null，不记0或通过；实验不会向真实用户发布。相关性/忠实度聚合只有已完成的LLM评分参与，引用聚合只来自规则结果；不同输入集合不可默认为同一评估数据集。

原型检查器只对synthetic seed作显式正式DTO投影：补足固定技术元数据并将展示短时间映射到样例日期。正式Gateway不使用该投影生成运行事实。可重复检查：`cd docs/releases/v1.0.0/draft/prototype && npm run check:contract`。

会话期限、保留期、风险阈值、受信代理和原子配额必须按实施说明由真实后端验证；字段齐全或样例验证通过均不替代生产环境证据。
