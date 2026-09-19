# v1.0.0/b002 后端接口清单（用户接受的实现交接，外部服务待最终验收）

权威输入为 [b002 OpenAPI][contract]、[REQ/AC 映射][trace]；manifest SHA-256 为 `420ebd837df8c239cc1b3ecd4b6509ca1ebca98a3fbeaf6fba4efde2fb58e3d3`。下表覆盖全部 53 个 operationId。路径均加 `/api/v1`。正式前端尚未实施，“前端操作”是批准的消费者需求，不表示页面已交付。

`T53` 为 [test_runtime_contract.py][T53] 的 `test_all_frozen_operations_return_their_real_http_contract`：按 operationId 发真实 Gateway/MySQL 请求，检查成功状态、JSON schema、204 或 SSE。测试记录明确为 synthetic；模型连接仅验证无密钥时 `verified:false`；202 仅证明受理，不证明 worker 或外部服务成功。请求样例可复现 T53 中同名操作。错误样例是契约预期，具体已执行路径见每行补充证据及 [Error 契约测试][Errors]，不能把样例本身计为实测。

请求约定：浏览器 `credentials: include`；用户/管理员分别为 `zg_session` / `zg_admin_session` Cookie。所有写请求带 `X-Zhige-Request: 1`，JSON 带 `Content-Type: application/json`。表内 `I` 表示另带 `Idempotency-Key: synthetic-request-0001`：新意图换值，原意图重试沿用。同键不同内容为 E-CONFLICT。除建立匿名会话和管理员登录外均检查对应角色；跨用户资源返回 404。仅允许配置的 Origin，跨源或缺失写入专用头为 E-CSRF。

所有样例文件均为 synthetic，HTTP body 取文件 `.data`，不带 `synthetic/schema` 外壳。`Page(X)` 是 `{"items":[X.data],"nextCursor":null}`；空结果 `{"items":[],"nextCursor":null}`。`Write(X)` 只取对应 OpenAPI 写 schema 允许字段：Model 去 `id/keyMasked/enabled/verified`，Config 去 `id/version/status`，EvalCase 去 `id/revision`。表内 DTO 状态描述覆盖示例的特定字段，其余完整形状由链接给出。分页 `limit=1..100`，cursor 不透明；非法输入为 E-VALID。鉴权接口通用错误包括会话失效 E-AUTH、停用 E-BLOCK、限流 E-RATE、依赖不可用 E-UNAVAILABLE；各行补充其重要业务错误。

## 会话、偏好与用户内容（20 个操作）

| 操作与路由 | REQ / AC | 前端操作及请求样例 | 成功 / 错误样例 | 实现 / 证据 |
| --- | --- | --- | --- | --- |
| `ensureAnonymousSession` · `POST /auth/anonymous` | REQ-AUTH-001、REQ-ABUSE-001 / AC-BE-002、016 | 欢迎页自动建立/恢复身份；无 body | 200 [Session][session] + Set-Cookie；E-BLOCK / E-RATE | [Application][A]；T53；[API][API] Cookie/hash/封禁测试；[Linux 冒烟][runtime] |
| `getSession` · `GET /auth/session` | REQ-AUTH-001 / AC-BE-002 | 刷新恢复身份/onboarding；无 body | 200 [Session][session]；E-AUTH / E-BLOCK | A；T53；API 会话恢复/过期 Cookie |
| `adminLogin` · `POST /admin/auth/login` | REQ-AUTH-001 / AC-BE-002、017 | 管理员登录；`{"email":"synthetic-admin@example.invalid","password":"synthetic-password"}` | 200 `{"kind":"admin","userId":"synthetic-admin","name":"示例管理员"}` + 管理 Cookie；E-AUTH / E-RATE | A；T53；API 独立管理 Cookie；runtime |
| `getAdminSession` · `GET /admin/auth/session` | REQ-AUTH-001 / AC-BE-002、017 | 管理控制台恢复身份；无 body | 200 AdminSession（同上）；匿名 E-FORBID | A；T53；API 每个管理读接口权限 |
| `adminLogout` · `DELETE /admin/auth/session` | REQ-AUTH-001 / AC-BE-002 | 管理员退出；无 body | 204 空响应并清 Cookie；E-FORBID / E-CSRF | A；T53 |
| `getPreferences` · `GET /me/preferences` | REQ-PREF-001 / AC-BE-003 | 引导/设置加载三字段和 version；无 body | 200 [Preferences][pref]；E-AUTH | A；T53；API 偏好/onboarding 原子持久化 |
| `savePreferences` · `PUT /me/preferences` | REQ-PREF-001、REQ-BRIEF-001 / AC-BE-003 | 显式保存；`{"version":0,"topics":["Agent"],"role":"示例背景","keywords":[]}` | 200 [Preferences][pref]（新 version）；空话题且空关键词 E-VALID；旧版本 E-CONFLICT | A；T53；API CAS/两并发仅一个成功 |
| `getDeliverySettings` · `GET /me/delivery-settings` | REQ-DELIVERY-001 / AC-UI-007、AC-INT-002 | 个人设置推送时间；无 body | 200 [DeliverySettings][setting]；E-AUTH | A；T53；API 仅时间字段 |
| `saveDeliverySettings` · `PUT /me/delivery-settings` | REQ-DELIVERY-001 / AC-UI-007、AC-INT-002 | 保存每日时间；`{"time":"09:35"}` | 200 [DeliverySettings][setting]；非法时间/多余字段 E-VALID | A；T53；API 不即时生成；[Workers][Workers] 改时间不补历史 |
| `listMemories` · `GET /me/memories` | REQ-MEM-001、REQ-AUTH-001 / AC-BE-010、002 | 保留本人记忆 API；本版无记忆管理 UI；`?limit=20` | 200 Page([Memory][memory])；E-AUTH | A；T53；API 分页/秘密不回显 |
| `deleteMemory` · `DELETE /me/memories/{id}` | REQ-MEM-001、REQ-AUTH-001 / AC-BE-010、002 | 本人记忆 API；本版无 UI 入口；path 为本人 id | 204 空响应；非本人/不存在 E-NOTFOUND | A；T53；API 记忆归属 |
| `listBriefs` · `GET /me/briefs` | REQ-BRIEF-001、REQ-AUTH-001 / AC-BE-003、002、014 | 今日/历史搜索、主题/日期/状态及翻页；`?q=Agent&limit=20` | 200 Page([Brief][brief])；空结果空 Page；E-VALID | A；T53；API 归属/分页；[Execution][Execution] 空匹配不造新闻 |
| `generateBrief` · `POST /me/briefs` · I | REQ-BRIEF-001、REQ-AGENT-002、REQ-OBS-001、REQ-ABUSE-001 / AC-BE-003、010、014、016 | 今日手动生成；`{"preferenceVersion":1}` | 202 [排队进度][queued]；E-CONFLICT / E-RATE / E-UNAVAILABLE | A；T53；API 幂等/并发/每日配额；Execution（模型 synthetic） |
| `getBrief` · `GET /me/briefs/{id}` | REQ-BRIEF-001、REQ-AUTH-001、REQ-OBS-001 / AC-BE-003、002、014 | 简报详情及新闻弹窗；无 body | 200 [Brief][brief] 或 [partial][partial]；未发布/非本人 E-NOTFOUND | A；T53；API 归属；Execution/Workers 发布后公开 |
| `getCurrentGeneration` · `GET /me/generations/current` | REQ-AGENT-002、REQ-OBS-001 / AC-BE-010、014 | 刷新恢复最近一次生成；不依赖本地 id | 200 [进度][progress]，从未生成为 JSON `null`；E-AUTH | A；T53；API 恢复；Execution 发布前95%、发布后100% |
| `getGenerationProgress` · `GET /me/generations/{id}` | REQ-AGENT-002、REQ-OBS-001、REQ-AUTH-001 / AC-BE-010、014、002 | 轮询进度/预计时间；无 body | 200 [进度][progress]，未知估计 [null][queued]；非本人 E-NOTFOUND | A；T53；API 跨用户；Execution 公开进度边界 |
| `cancelGeneration` · `POST /me/generations/{id}/cancel` | REQ-AGENT-002、REQ-OBS-001、REQ-AUTH-001 / AC-BE-010、014、002 | 取消本人生成；无 body | 202 GenerationProgress（活动态 `cancelling`，终态保持）；E-NOTFOUND | A；T53；Execution 排队/运行中取消 |
| `listOwnDeliveries` · `GET /me/deliveries` | REQ-DELIVERY-001、REQ-AUTH-001 / AC-UI-008、AC-BE-002、AC-INT-002 | 本人的站内发布结果；`?limit=20` | 200 Page([Delivery][delivery])；E-AUTH | A；T53；API 归属；Workers 发布/重投 |
| `retryOwnDelivery` · `POST /me/deliveries/{id}/retry` · I | REQ-DELIVERY-001、REQ-AUTH-001 / AC-UI-008、AC-BE-002、AC-INT-002 | 重试本人失败发布；无 body | 202 [Delivery][delivery]（同 briefId、待发 `pending`）；非本人 E-NOTFOUND | A；T53；API 归属；Workers 不再生成简报 |
| `getOverview` · `GET /admin/overview` | REQ-OBS-001 / AC-BE-014 | 管理总览；无 body | 200 `{"activeRuns":0,"failedSources":0,"failedDeliveries":0,"sampleCount":0,"completionRate":null,"generatedAt":"2026-09-18T00:00:00Z"}`；E-FORBID | A；T53；API 管理权限 |

## 来源、模型与配置（17 个操作）

| 操作与路由 | REQ / AC | 前端操作及请求样例 | 成功 / 错误样例 | 实现 / 证据 |
| --- | --- | --- | --- | --- |
| `listSources` · `GET /admin/sources` | REQ-SRC-001、REQ-SRC-002 / AC-BE-004、005 | 来源列表、周期/缓存/失败；`?limit=20` | 200 Page([Source][source])；E-FORBID / E-VALID | A；T53；[Ingestion][Ingestion]/Workers；[真实采集][live-ingestion] |
| `createSource` · `POST /admin/sources` | REQ-SRC-001、REQ-SRC-002 / AC-BE-004、005 | 新增源；`{"name":"示例RSS","kind":"rss","sourceId":"","url":"https://fixture.invalid/feed.xml","interval":900}` | 201 [Source][source]（新源采集字段 null）；未知源/非法字段 E-VALID | A；T53；Ingestion 上游周期 |
| `saveSource` · `PUT /admin/sources/{id}` | REQ-SRC-001、REQ-SRC-002 / AC-BE-004、005 | 编辑来源；body 同创建 | 200 [Source][source]；未知 E-NOTFOUND、采集中 E-STATE | A；T53；Workers 并发租约 |
| `getSource` · `GET /admin/sources/{id}` | REQ-SRC-001、REQ-SRC-002 / AC-BE-004、005 | 来源详情/最近快照；无 body | 200 [Source][source] 或 [失败快照][source-failed]；E-NOTFOUND | A；T53；Ingestion/Workers；live-ingestion |
| `setSourceEnabled` · `PUT /admin/sources/{id}/enabled` | REQ-SRC-001、REQ-SRC-002 / AC-BE-004、005 | 启停来源；`{"enabled":false}` | 200 Source（enabled 已更新）；E-NOTFOUND | A；T53 启停两次；Workers 到期调度 |
| `fetchSource` · `POST /admin/sources/{id}/fetch` · I | REQ-SRC-001、REQ-SRC-002 / AC-BE-004、005 | 立即采集；无 body | 202 [Source][source]（仅受理）；停用 E-STATE | A；T53 受理；Workers 调度；live-ingestion 真 HTTP/快照 |
| `listModels` · `GET /admin/models` | REQ-ADMIN-001 / AC-BE-013 | 模型列表/角色/启停/验证；`?limit=20` | 200 Page([ModelConfig][model])；E-FORBID / E-VALID | A；T53；API 密钥不回显 |
| `createModel` · `POST /admin/models` | REQ-ADMIN-001 / AC-BE-013 | 新建模型；Write([ModelConfig][model])，可另传 `apiKey:"synthetic-secret"` | 201 ModelConfig，无原密钥；E-VALID | A；T53；API 密钥加密；真实连接 blocked |
| `saveModel` · `PUT /admin/models/{id}` | REQ-ADMIN-001 / AC-BE-013 | 编辑/替换 key；Write(ModelConfig)，不传 key 保留秘密 | 200 [ModelConfig][model]，只返回 masked；E-NOTFOUND / E-VALID | A；T53；API 替换不回显 |
| `setModelEnabled` · `PUT /admin/models/{id}/enabled` | REQ-ADMIN-001 / AC-BE-013 | 启停模型；`{"enabled":false}` | 200 ModelConfig；E-NOTFOUND | A；T53 |
| `testModel` · `POST /admin/models/{id}/test` | REQ-ADMIN-001 / AC-BE-013 | 触发真实能力探针；无 body | 已验 HTTP 200 失败结果：`{"verified":false,"message":"请先配置模型密钥","testedAt":"2026-09-18T00:00:00Z","capabilities":[]}`；中途配置变更 E-CONFLICT | [Gateway][G] `model_test`；T53 无 key；[live-services][live] 模型成功 blocked，HTTP 200 不代表能力通过 |
| `revokeModelSecret` · `DELETE /admin/models/{id}/secret` | REQ-ADMIN-001 / AC-BE-013 | 撤销 key；无 body | 204 空响应，后续模型未验证；E-NOTFOUND | A；T53；API 密钥撤销 |
| `listConfigs` · `GET /admin/agent-configs` | REQ-ADMIN-002 / AC-BE-013 | 草稿/已发布配置列表；`?limit=20` | 200 Page([AgentConfig][config])；E-FORBID / E-VALID | A；T53；API published 不可变 |
| `createConfig` · `POST /admin/agent-configs` | REQ-ADMIN-002 / AC-BE-013 | 新建提示词/工具/预算等草稿；Write([AgentConfig][config]) | 201 AgentConfig（draft）；非法预算/字段 E-VALID | A；T53；API published 不可变 |
| `saveConfig` · `PUT /admin/agent-configs/{id}` | REQ-ADMIN-002 / AC-BE-013 | 保存草稿；Write(AgentConfig) | 200 AgentConfig；已发布 E-STATE、未知 E-NOTFOUND | A；T53；API 不可变；Execution 固定快照 |
| `publishConfig` · `POST /admin/agent-configs/{id}/publish` | REQ-ADMIN-002、REQ-ADMIN-001 / AC-BE-013 | 发布并提示新运行生效；无 body | 200 AgentConfig（published）；模型未启用/验证 E-STATE | A；T53 使用 synthetic verified 模型；API 不可变；实际模型前置 blocked |
| `listAdminRuns` · `GET /admin/runs` | REQ-OBS-001、REQ-AGENT-002 / AC-BE-014、010 | 运行列表/状态/模型/时间过滤；`?status=failed&limit=20` | 200 Page([AgentRun][run])；E-FORBID / E-VALID | A；T53；API 用户无运行 API；Execution |

## 运行、评估、发布与匿名监测（16 个操作）

| 操作与路由 | REQ / AC | 前端操作及请求样例 | 成功 / 错误样例 | 实现 / 证据 |
| --- | --- | --- | --- | --- |
| `getAdminRun` · `GET /admin/runs/{id}` | REQ-OBS-001、REQ-AGENT-002 / AC-BE-014、010 | 管理运行详情/工具/压缩/子任务；无 body | 200 [AgentRun][run]，未知用量 null；E-NOTFOUND / E-FORBID | A；T53；Execution 持久事件/脱敏；[Harness][Harness] |
| `cancelAdminRun` · `POST /admin/runs/{id}/cancel` | REQ-AGENT-002、REQ-OBS-001 / AC-BE-010、014 | 管理员取消运行；无 body | 202 AgentRun（活动态 cancelling）；E-NOTFOUND / E-FORBID | A；T53；Execution 取消；Harness 子任务共享取消 |
| `adminRunEvents` · `GET /admin/runs/{id}/events` | REQ-OBS-001、REQ-MSG-001 / AC-BE-014、011 | SSE 断线恢复带 `Last-Event-ID: 1` | 200 text/event-stream，见下方样例；非法游标 E-VALID、匿名 E-FORBID、未知 E-NOTFOUND | G；T53 只回放 id2、run.event、逐事件 schema；Execution journal 单调/去重 |
| `listEvalCases` · `GET /admin/eval-cases` | REQ-EVAL-001 / AC-BE-015 | 固定评估用例列表；`?limit=20` | 200 Page([EvalCase][case])；E-FORBID / E-VALID | A；T53；[Evaluation][Evaluation] 固定输入 |
| `createEvalCase` · `POST /admin/eval-cases` | REQ-EVAL-001 / AC-BE-015 | 新建固定来源/偏好/时钟；Write([EvalCase][case]) | 201 EvalCase；E-VALID | A；T53；Evaluation 快照/hash |
| `saveEvalCase` · `PUT /admin/eval-cases/{id}` | REQ-EVAL-001 / AC-BE-015 | 修改用例 revision 增加；Write(EvalCase) | 200 EvalCase；未知 E-NOTFOUND | A；T53 实验冻结 revision2，之后 revision3 不回写 |
| `runEvaluation` · `POST /admin/evaluations` · I | REQ-EVAL-001 / AC-BE-015 | 选配置发起实验；`{"configVersion":"v1"}` | 202 `{"evaluationId":"synthetic-evaluation-01"}`；空数据集 E-VALID、未发布 E-STATE、模型不可用 E-UNAVAILABLE | A；T53 受理/快照；Evaluation 分离评分；真实 provider/judge blocked |
| `listEvaluations` · `GET /admin/evaluations` | REQ-EVAL-001 / AC-BE-015 | 实验列表/结果比较；`?limit=20` | 200 Page([Evaluation][eval])；E-FORBID / E-VALID | A；T53；Evaluation 失败评分 null |
| `getEvaluation` · `GET /admin/evaluations/{id}` | REQ-EVAL-001 / AC-BE-015 | 实验详情/评分来源；无 body | 200 [排队][eval-pending] 或 [结果][eval]；E-NOTFOUND | A；T53 排队值 null；Evaluation controlled callback 不代表真实 judge |
| `listAdminDeliveries` · `GET /admin/deliveries` | REQ-DELIVERY-001 / AC-UI-008、016、AC-INT-002 | 管理发布列表/失败处理；`?limit=20` | 200 Page([Delivery][delivery])；E-FORBID / E-VALID | A；T53；Workers 提交/重投 |
| `retryAdminDelivery` · `POST /admin/deliveries/{id}/retry` · I | REQ-DELIVERY-001 / AC-UI-008、016、AC-INT-002 | 重试原简报发布；无 body | 202 Delivery（同 briefId、pending）；E-NOTFOUND / E-FORBID | A；T53；Workers/Execution 不重新生成 |
| `listAnonymousAccounts` · `GET /admin/anonymous-accounts` | REQ-ABUSE-001、REQ-AUTH-001 / AC-BE-016、017 | 监测计数/风险/脱敏来源；`?limit=20` | 200 Page([AnonymousAccount][account])；E-FORBID / E-VALID | A；T53；API quota/风险/脱敏 |
| `setAnonymousAccountStatus` · `PUT /admin/anonymous-accounts/{id}/status` | REQ-ABUSE-001、REQ-AUTH-001 / AC-BE-016、017 | 封禁/解封；`{"status":"blocked","reason":"示例管理操作"}` | 200 AnonymousAccount（status 更新）；E-NOTFOUND / E-VALID | A；T53 blocked→active；API Cookie 不换号；Workers 停止调度/发布 |
| `listAbuseEvents` · `GET /admin/abuse-events` | REQ-ABUSE-001、REQ-AUTH-001 / AC-BE-017 | 风险/限流/管理审计；`?limit=20` | 200 Page([AbuseEvent][abuse])；E-FORBID / E-VALID | A；T53；API 真实请求触发风险事件 |
| `getAnonymousPolicy` · `GET /admin/anonymous-policy` | REQ-ABUSE-001 / AC-BE-016、017 | 当前有效配额；无 body | 200 [AnonymousPolicy][policy]；E-FORBID | A；T53；API MySQL quota bucket |
| `saveAnonymousPolicy` · `PUT /admin/anonymous-policy` | REQ-ABUSE-001 / AC-BE-016、017 | 保存配额；body 为 [AnonymousPolicy.data][policy] | 200 AnonymousPolicy；非法额度 E-VALID / 跨源 E-CSRF | A；T53 保存/审计；API 429；解封仍受额度 |

## 错误与 SSE 样例

下面是合成请求的预期错误；全部符合冻结 Error schema。requestId 实际由 Gateway 生成并对应 X-Request-ID；message 只供用户阅读，客户端按状态码/code 处理。内部错误原因不作为契约之外的 code 透出。Gateway 对实际 Error body 做 schema 校验；[错误测试][Errors] 与 [独立 JUnit][error-junit] 验证 public_code 映射和真实 HTTP 错误响应。

| 标识 | HTTP 与 body 样例 | 客户端动作 |
| --- | --- | --- |
| E-AUTH | 401 `{"code":"UNAUTHENTICATED","message":"会话已失效","requestId":"synthetic-error-01"}` | 用户重建会话/管理员登录；不声称找回丢失 Cookie 身份 |
| E-FORBID | 403 `{"code":"FORBIDDEN","message":"没有访问权限","requestId":"synthetic-error-02"}` | 显示无权限 |
| E-BLOCK | 403 [Error ACCOUNT_BLOCKED][blocked] | 显示停用，禁止循环建立替代账号 |
| E-CSRF | 403 `{"code":"CSRF_REJECTED","message":"请求来源校验失败","requestId":"synthetic-error-03"}` | 显示失败，检查部署 Origin/请求头 |
| E-VALID | 400 `{"code":"VALIDATION_ERROR","message":"输入内容不符合要求","requestId":"synthetic-error-04"}` | 保留输入，显示字段问题 |
| E-NOTFOUND | 404 `{"code":"NOT_FOUND","message":"记录不存在","requestId":"synthetic-error-05"}` | 不区分不存在与他人资源 |
| E-CONFLICT | 409 [Error VERSION_CONFLICT][conflict] | 重读且保留草稿；同幂等键内容冲突时换新意图 |
| E-STATE | 409 `{"code":"INVALID_STATE","message":"当前状态不能执行此操作","requestId":"synthetic-error-06"}` | 刷新状态；已发布配置新建草稿 |
| E-RATE | 429 + `Retry-After: 15`；`{"code":"RATE_LIMITED","message":"请求过于频繁","requestId":"synthetic-error-07"}` | 等待，不显示为已排队 |
| E-UNAVAILABLE | 503 `{"code":"DEPENDENCY_UNAVAILABLE","message":"服务暂时不可用","requestId":"synthetic-error-08"}` | 保留旧数据/草稿，允许重试，不展示成功 |

SSE 合成样例：同一 run 的 id 单调，不包含密钥或私有思维链。

```text
id: 2
event: run.event
data: {"id":2,"time":"2026-09-18T00:00:00Z","title":"Synthetic persistent event","detail":"Synthetic contract-only fixture","status":"completed","duration":"1ms"}

```

## 证据边界

[后端 JUnit][junit] 记录已执行测试；[Linux 冒烟][runtime] 记录真实 API、MySQL、Redis→Celery tick 和 worker 内 Docker 沙箱；[真实采集][live-ingestion] 记录两个 NewsNow 与一个 RSS 的 HTTP/快照。T53、错误测试、worker/execution 和外部集成证据各自证明不同边界。

[live-services][live] 当前明确 live-model、live-tavily 为 blocked。真实模型 capability 成功、生成/用量、Tavily 搜索、真实 LLM 评分及完整实际生成发布闭环未通过。ScriptedModel 用于验证实际 create_agent/LangGraph、MySQL、文件、预算、取消与发布逻辑，不能证明 provider 成功；冻结 evaluation-completed.json 也不是实际评分结果。本文件是交接候选，不能据此接收后端或开始正式前端。阶段报告应绑定最终代码指纹与最后一次实际测试证据。

[contract]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/openapi.json
[trace]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/traceability.json
[A]: ../../../../backend/src/zhigenews/application.py
[G]: ../../../../backend/src/zhigenews/gateway.py
[T53]: ../../../../backend/tests/test_runtime_contract.py
[API]: ../../../../backend/tests/test_api.py
[Errors]: ../../../../backend/tests/test_errors.py
[Workers]: ../../../../backend/tests/test_workers.py
[Execution]: ../../../../backend/tests/test_execution.py
[Ingestion]: ../../../../backend/tests/test_ingestion.py
[Evaluation]: ../../../../backend/tests/test_evaluation.py
[Harness]: ../../../../backend/tests/test_harness_runtime.py
[junit]: ../evidence/backend-junit.xml
[error-junit]: ../evidence/backend-error-contract-junit.xml
[runtime]: ../evidence/runtime-smoke.json
[live-ingestion]: ../evidence/ingestion-live.json
[live]: ../evidence/live-services.json
[session]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/session-anonymous.json
[pref]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/preferences.json
[setting]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/delivery-settings.json
[memory]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/memory.json
[brief]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/brief-public.json
[partial]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/brief-partial.json
[queued]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/generation-estimating.json
[progress]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/generation-running.json
[delivery]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/delivery-failed.json
[source]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/source-newsnow.json
[source-failed]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/source-rss-failed.json
[model]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/model.json
[config]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/agent-config.json
[run]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/run-partial.json
[case]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/eval-case.json
[eval]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/evaluation-completed.json
[eval-pending]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/evaluation-pending.json
[account]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/anonymous-account.json
[abuse]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/abuse-rate-limited.json
[policy]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/anonymous-policy.json
[conflict]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/error-conflict.json
[blocked]: ../../../../docs/releases/v1.0.0/baselines/b002/snapshot/contracts/examples/error-account-blocked.json


本次交接基线为v1.0.0/b003；相较b002仅调整验收责任/时点，API契约字节与后端源码均相同，故文中b002契约链接仍为同一接口定义。用户原话与未验证项见evidence/user-acceptance-arrangement.json及backend-verification.json。
