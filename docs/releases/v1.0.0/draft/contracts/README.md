# v1.0.0 交换契约（ITERATE r5 草稿）

唯一交换主源为 [openapi.json](openapi.json)，OpenAPI 3.1 / JSON Schema 2020-12；当前50 schemas、52操作、22个synthetic固定样例。尚未冻结，正式HTTP Gateway未实现。原型 `/__demo` 是独立的开发服务命名空间，不能当作正式API。

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
| 取消生成 | POST /me/generations/{id}/cancel | 服务能力；先cancelling，由worker确认cancelled，不改变每日计划 |
| 本人记忆/发布服务 | /me/memories、/me/deliveries | 保留原服务能力，用户设置不展示记忆控件，发布重试不重新生成 |
| 来源/模型/配置/评估/发布 | /admin/sources、models、agent-configs、evaluations、deliveries等 | 保持既有管理契约；key只写不回显 |
| 管理运行 | /admin/runs、/{id}、/{id}/cancel、/{id}/events | 管理员检查、SSE回放，普通用户不可访问 |
| 匿名监测 | GET /admin/anonymous-accounts，PUT /{id}/status | 脱敏监测，active/blocked和1–200字原因；管理审计 |
| 风险事件/策略 | GET /admin/abuse-events，GET/PUT /admin/anonymous-policy | 真实统计与限流，策略整数范围见schema |

已删除用户注册/密码登录写接口、`/me/news/{id}/read`及全部`/me/runs*`。旧管理/users转换为匿名监测接口。旧用户页面链接可重定向，但不保留泄露运行过程的HTTP兼容接口。契约未发布，无生产旧客户端迁移；历史要求见spec/07-changes.md。

## 身份、滥用与错误

服务器生成不透明token，仅Set-Cookie传递，生产HttpOnly/Secure/SameSite=Lax/Path=/；保存哈希并执行过期和撤销。同Cookie保持个人偏好、历史和完成标记；Cookie丢失形成新身份，无密码恢复路径。被封禁会话403不自动换号；匿名用户拥有全部用户端功能，但所有管理路由使用独立adminSessionCookie。跨账号资源404，客户端userId声明不作为授权依据。

写操作检查允许的Origin和CSRF（JSON/专用头或服务端token），SameSite不单独承担CSRF保护；配置明确的凭据CORS源。具体依据和生产/开发差异见[架构](../spec/04-architecture.md)。

错误统一 `{code,message,requestId,fields?}`。400输入错误、401会话失效、403角色/ACCOUNT_BLOCKED/CSRF_REJECTED、404不可见、409版本/幂等冲突、429配额、503依赖不可用。429必须返回Retry-After秒数，前端停止立即重试。

账号每分钟请求、每日生成与并发，另有同IP新账号速率；默认60、20、1、10，范围分别1–600、1–100、1–10、1–100。服务器原子判定并入队，重复幂等请求不重复扣配额；封禁停止新生成/后续调度，解封不重置限制。清Cookie不重置IP桶。监测只含脱敏IP标签、计数、风险与原因，禁止token/原始IP泄漏；封禁、解封及策略修改记录管理员审计。

创建生成、发布重试、采集、实验使用Idempotency-Key；同身份/路由/key/body返回原操作，同key不同body409。SSE只在管理域，Last-Event-ID不是权限凭证。

## 冻结前清单

RunEvent.time仍是原型短文本，真实事件须完整时间；AgentRun未知用量需可空，不把0解释成真实成本。NewsItem仍待补采集时间/快照引用；评估仍待dataset/评分器版本和逐项结果。正式会话期限、清理保留期、风险阈值、受信代理和原子配额实现需在后端阶段明确验证。上述未实施，不以本轮Cookie演示或契约通过冒充生产验收。
