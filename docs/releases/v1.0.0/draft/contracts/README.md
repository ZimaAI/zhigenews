# v1.0.0 交换契约（ITERATE 草稿）

唯一交换主源为 [openapi.json](openapi.json)，OpenAPI 3.1 / JSON Schema 2020-12。当前未冻结，也未实现 HTTP Gateway；原型使用 `../prototype/shared/mock.ts` 的内存 adapter。HTTP 路由表达拟采用的服务边界，不能把原型操作成功当作接口已实现。

## 类型与固定样例

核心响应 schema 与 `../prototype/shared/types.ts` 的同名接口字段对齐，采用 camelCase；`DemoState`、`Scenario`、toast、局部表单和筛选属于页面状态，不是后端响应。`DemoUser` 是原型沿用名称，正式命名调整应同时更新契约、生成类型和 adapter。

原型已有的枚举保持一致：来源为 `rss/newsnow/search`，其中 `search` 使用 Tavily 的 `web_search` 工具；用户偏好仅话题/背景/关键词；模型角色为 `主模型/摘要模型/评估模型/子模型`。Source 的 `interval/upstreamInterval` 单位为**秒**，界面可换算为分钟。评估相关性/忠实度为 0–5，引用检查为 0–100%，费用为估算美元，延迟为秒。

`examples/*.json` 均采用 `{ "synthetic": true, "schema": "SchemaName", "data": ... }` 封套；只将 `data` 按 `components.schemas[schema]` 校验。新闻内容是模拟材料，`.example.com` URL 仅示意，不作为真实可访问新闻。原型页面 seed 中的文档链接也只是参考资料，不能据此声称当天发布了某条新闻。

当前固定样例覆盖 Preferences、NewsItem、Brief、AgentRun、DeliverySettings、Delivery、Source、ModelConfig、AgentConfig、Evaluation、Memory 和 Error，包括未知发布时间、来源失败、部分完成、投递失败与待评分空值。`prototype/shared/fixtures.ts` 为交互 seed；不得把它变成第二个交换规范。当前类型手写并通过校验与契约同步；正式客户端/DTO 须从契约生成，或持续校验字段、枚举、样例与响应。

## adapter 到 Gateway 的映射

所有路由前缀为 `/api/v1`。读取列表使用 `{items,nextCursor}` 分页封套，adapter 聚合到各自页面状态。

| 内存方法 | 拟采用的 HTTP 操作 | 边界说明 |
| --- | --- | --- |
| `load` | `GET /auth/session`、本人资源或管理员列表 | 不提供一个向普通用户暴露所有管理数据的 `/state` |
| `login/logout/register` | `POST/DELETE /auth/session`、`POST /auth/register` | 注册仅创建普通用户；原型身份是模拟 |
| `savePreferences` | `PUT /me/preferences` | PreferencesWrite 提交当前 version 和三字段，冲突 409；成功递增并原子标记 onboardingCompleted |
| `saveDelivery` | `PUT /me/delivery-settings` | 请求/响应只有 time，每日站内发布，系统时区 Asia/Shanghai |
| `deleteMemory` | `DELETE /me/memories/{id}` | 只删本人资源 |
| `generateBrief/cancelRun` | `POST /me/briefs`、`/me/runs/{id}/cancel` | 生成返回 runId，取消先进入 cancelling |
| `markRead` | `PUT /me/news/{id}/read` | adapter 将 toggle 转换为显式 `{read}` |
| `retryDelivery` | `POST /me/deliveries/{id}/retry` 或 admin 对应路由 | adapter 若收到 briefId，先解析该简报的投递 ID，HTTP 不混用两种 ID |
| `saveSource/toggleSource/fetchSource` | `POST/PUT /admin/sources`、`/{id}/enabled`、`/{id}/fetch` | 采集状态由后端返回；toggle 转显式 enabled |
| `saveModel/testModel/toggleModel` | `POST/PUT /admin/models`、`/{id}/test`、`/{id}/enabled` | key 参数映射 write-only apiKey；keyMasked 不可写；撤销走 DELETE `/{id}/secret` |
| `saveConfig/publishConfig` | `POST/PUT /admin/agent-configs`、`/{id}/publish` | 只能修改草稿，发布后为不可变版本 |
| `saveEvalCase/runEvaluation` | `POST/PUT /admin/eval-cases`、`POST /admin/evaluations` | 运行返回 evaluationId；固定样例实验不向用户发布简报 |
| `toggleUser` | `PUT /admin/users/{id}/status` | 转显式 active/disabled，后端验证管理员 |

`PreferencesWrite/SourceWrite/ModelWrite/ConfigWrite/DeliverySettingsWrite/EvalCaseWrite` 与响应 DTO 分离；adapter 只投递允许写入字段。连接测试返回能力验证结果，不能只凭 HTTP 200 标记支持全部工具。

## 鉴权、错误与幂等

拟采用服务端会话 Cookie（HttpOnly/Secure/SameSite），变更请求校验来源/CSRF。401 为未登录或会话过期，403 为角色禁止；本人作用域的跨用户资源返回 404，避免泄露存在性。管理员路由必须服务端检查角色，按钮隐藏不能代替授权。密钥只写，不在配置读取、事件、错误或运行 checkpoint 中回显。

错误统一为 `{code,message,requestId,fields?}`。400 为可定位的输入错误，409 为版本/状态/幂等冲突，429 为额度限制，503 为依赖不可用。原型目前抛 `Error` 供页面保留输入与显示错误，尚未完成真实 HTTP 错误映射。

新生成、站内发布重试、手动采集和实验创建要求 `Idempotency-Key`；同身份/路由/key/请求体重放返回原操作，不生成重复工作。相同 key 搭配不同请求体返回 409。新一次用户意图使用新 key。SSE 的 event ID 在同一 run 内递增，`Last-Event-ID` 用于补拉；不是会话权限凭证。

## 冻结前仍须细化

当前契约刻意对齐可运行原型，尚不能代替完整后端规范：`RunEvent.time` 是页面时间文本；正式事件将补充或替换为完整时间 DTO。DeliverySettings 仅 time，下一次 UTC 调度时刻由后端内部计算。Source 的未知时间为空串是原型兼容约定，持久层使用 null。

原型 `AgentRun` 数值字段不能表达未知用量，未知不能按 0 成本解释；正式 DTO 需可空指标与估算说明。NewsItem 尚需补采集时间/快照来源 ID；评估详情尚需 dataset 版本、评分器/人工来源与逐项结果；持久消息日志、摘要、文件工具返回和运行配置快照属于后端契约细化范围。以上在 SPECIFY 冻结前与原型/类型同步，不以默认值冒充已采集事实。


## r3 用户反馈与未冻结契约调整

Preferences 只保留 version、role、topics、keywords；未配置读取可为 version 0 和空数组，PreferencesWrite 至少一个话题或关键词。背景最长 500 字；关键词最多 20 个，每个最长 40 字。version 是服务端并发字段，不是可编辑偏好。删除的排除词、匹配模式、来源、语言、窗口、条数与深度不再由用户提交；Harness 仍可使用管理员参数与系统默认值。

Session 新增必填 onboardingCompleted：注册为 false，第一次有效偏好保存与标记 true 在同一事务内提交，刷新/登录保留。原型 DemoState 保存该投影；真实前端应读取 Session，不能根据浏览器历史或已有简报推断。

DeliverySettings 与写请求只有 time；每日自动、系统时区 Asia/Shanghai、仅 in_app。DeliveryStatus.submitted 在此渠道表示站内已发布，不代表已读。删除 `/me/email-verification`、`/me/email-verification/confirm`、`/me/delivery-test` 和两种验证 schema；账号登录邮箱保留。当前 47 schemas、51 操作、14 个固定样例。契约尚未冻结，无生产旧客户端迁移；正式实现不接受 r2 的已移除用户字段。
