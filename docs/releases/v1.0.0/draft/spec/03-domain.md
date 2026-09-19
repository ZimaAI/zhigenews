# 领域模型与数据边界

本规范对应用户已批准的 v1.0.0 r5 原型，冻结身份以工作流基线快照为准。权威交换格式见 `../contracts/openapi.json`；页面上的模拟运行、评分与投递不代表下列后端不变量已实现。

## 四类模型

| 层次 | 对象与职责 | 不应混入的内容 |
| --- | --- | --- |
| 领域 | 用户、偏好版本、来源/快照、运行/子任务、简报版本、投递尝试、配置版本、评估实验 | 组件是否展开、表单脏状态、toast |
| 交换 | Preferences/NewsItem/公开 Brief/GenerationProgress，以及仅管理员 AgentRun/AnonymousAccount 等 DTO，写请求、分页、错误、SSE | ORM 对象、密钥原文、宿主物理路径、模型私有思维链 |
| 页面 | DemoState、Scenario、筛选/页码、编辑草稿、loading/error、新闻弹窗与对比选项 | 不承担权限、调度、投递保证 |
| 持久化 | MySQL 主外键/唯一约束/版本、不可变文件快照、checkpoint、outbox 与事件日志 | 不解析格式化的页面时间作为调度依据 |

## 实体、关系与不变量

| 领域实体 | 身份与关系 | 主要不变量/交换映射 |
| --- | --- | --- |
| User / Session | User 有稳定 ID；Session 归属一个 User | 匿名用户与管理员会话分离；服务器创建不透明会话并通过 Cookie 持有；过期/撤销由服务器控制；`Preferences.role` 是背景而非授权角色；Session 返回持久化 onboardingCompleted |
| AnonymousAccount / AbuseEvent / AnonymousPolicy | 匿名用户稳定ID；事件关联账户，规则由管理员管理 | 同 Cookie 恢复身份；请求/每日生成/并发/同IP新建账号在服务端原子计数；封禁与解封审计；统计不含token或原始IP |
| GenerationProgress | 归属匿名用户的公开生成投影 | percent 与 remainingSeconds 可空；未知不报0或100；用户无 AgentRun/事件访问权；详情、状态与结果归属均服务端检查 |
| PreferenceRevision | `(userId, version)` 唯一 | 读取未配置偏好允许 version=0 和空数组；保存至少一个话题或关键词，成功递增并原子标记首次配置完成；仅话题/背景/关键词；旧运行保留原快照 |
| DeliveryPlan | 每用户一个计划 | 只有每日 HH:mm 可由用户修改；固定系统时区 Asia/Shanghai，首次偏好完成后默认启用；仅站内；对应 DeliverySettings |
| Source / SourceSnapshot | Source 稳定 ID；一个源有多次 Fetch 和不可变 Snapshot | NewsNow 与 RSS 分开；周期单位秒；成功发布新快照才能更新 lastSuccess；坏响应不覆盖有效快照；对应 Source |
| NewsEvidence / BriefItem | 条目带原 URL、来源及引用；BriefItem 归属某一期版本 | 来源发布时间可空，不能拿抓取/榜单时间替代；原文证据与 Agent 推荐理由分开；不存储已读/未读状态；对应 NewsItem/Citation |
| AgentConfigRevision / ModelEndpoint | 配置草稿发布成不可变版本并引用模型 | 模型 ID、端点、能力、密钥引用分离；API key 只写/加密保存；新运行绑定快照；对应 AgentConfig/ModelConfig |
| AgentRun / Subtask | run 归属用户与 thread；子 run 归属父 run | 绑定偏好/配置/来源快照；预算包括子任务；运行取消独立于未来计划；对应 AgentRun/Subtask |
| MessageJournal / Summary | `(threadId,messageSeq)` 单调唯一；调用实例关联 toolCallId | 原始日志保留，修复重建模型视图不重新编号；摘要另存覆盖范围与版本；最新用户原文不压缩 |
| BriefRevision | 简报归属用户与 run；日期内可有多个 version | 内容一经发布不可覆盖，引用及偏好快照可追溯；部分完成仍说明缺失来源；内部对应 AdminBrief；公开 Brief 不含 runId/偏好技术快照 |
| DeliveryAttempt | 归属精确 briefId/版本与渠道 | 生成完成不意味着站内发布成功；channel 固定 in_app；管理端重试复用同一简报并增加尝试；对应 Delivery |
| EvaluationDataset / EvaluationRun | 固定 case/来源快照与时钟；实验绑定配置与评分器版本 | 无评分为 null，非 0；规则/人工/LLM 分开；没有样本不显示准确率；对应 EvalCase/Evaluation |

## 状态与动作

2026-09-19 按用户要求移除 `UserMemory` 长期记忆模型及其保存、读取、删除和上下文注入能力。`MessageJournal / Summary` 仍属于当前线程，checkpoint 用于该线程恢复；用户显式偏好和既有简报独立保留。

运行通常为 `queued → running → completed/partial/failed`。取消为 `queued/running → cancelling → cancelled`，只有 worker 确认才显示已取消；终态不会因 SSE 断线改变。恢复在同一逻辑 run/thread 的 checkpoint 上继续，不能偷偷新建一次有副作用的工具执行。工具错误可被 Agent 处理后继续，单个失败事件不必等于整个 run 失败。

Source 使用 `unverified/healthy/syncing/failed/disabled`；发起采集只代表 syncing，解析并发布有效快照才 healthy。失败保留上一成功快照及其时间。Source 的 lastChanged 是本地检测到内容变化的时间，不是上游真实刷新时间。

配置为 `draft → published`；修改已发布配置应创建新草稿。停用模型不重写已经记录的历史版本，后续创建运行必须检查所引用模型是否仍可用。

站内发布使用 `disabled/pending/submitted/failed/unknown`。`submitted` 表示已发布，不能推断用户已读；超时无法确认发布事务则 unknown，由管理员核对后重试。disabled 仅供停用账户或历史状态，不是用户可选渠道。系统不集成邮件投递。

评估使用 `queued/running/completed/failed`；单项评分不可用为 null，不能记 0 或通过。原型的 completed 与分数均为模拟。

## 新简报、站内发布与调度

“立即生成/重新生成”是新的用户内容意图，创建新 run 与新 BriefRevision，并绑定当时最新偏好；老简报继续可读。重复点击同一次意图复用幂等键，不生成多个任务。

管理员“重试发布”沿用原 briefId 和内容版本，只增加发布尝试，不再次调用 Agent。修改偏好后重试仍发布旧简报；应用新偏好需要生成新简报。

首次有效偏好保存后每天自动调度，时间默认 08:00。用户只能改时间，取消本次运行不暂停每日计划。未完成首次配置和被禁用账户不调度；保存时间或恢复账户不补发过去的槽位。每日业务键包含用户、计划槽位和简报类型；队列至少一次投递，通过唯一约束和 outbox 避免重复创建及发布。

## 权限与时间

匿名用户可使用全部用户端功能，只读写本人的偏好、计划和简报，读取公开生成进度；管理员读管理视图与脱敏运行详情、管理来源/模型/配置和匿名账户。用户端不开放已读标记、整理记录、AgentRun或事件。服务端解析当前身份，不接收客户端声称的 userId 作为归属依据；用户作用域跨账号 ID 返回不可见。

数据库时间为 UTC；ISO 时间表示实际事件时刻，日期与每日 HH:mm 按系统时区 Asia/Shanghai 解释。用户不设置时区，后端保存完整下一次 UTC 计划时刻。原型固定时钟 `2026-09-18T08:12:00+08:00`，事件短时间是页面投影，不可直接持久化为调度事实。

新闻发布时间、采集成功时间、快照发布时间、简报生成时间、计划槽位和渠道提交时间分别记录；未知来源发布时间保留 null。严格新鲜度条件不能通过本地抓取时间补成“新新闻”。来源/运行工作区 ID 由服务端生成，不用外部标题或 URL 拼接目录。

## 匿名会话与公开生成投影

Session 只返回 kind=anonymous、userId、name、onboardingCompleted；token 只在 Set-Cookie 中返回，服务器只保存其哈希。匿名账户没有管理员权限，不允许用户提交userId声明所有权。同一Cookie刷新/重试不会新建账户，合法新会话的onboardingCompleted=false；已封禁会话返回403，不能通过自动重试创建替代账户。管理员采用独立Cookie和AdminSession。

GenerationProgress 的状态沿用运行终态语义，但不包含runId、模型、工具、事件、子任务、路径或配置。percent 为0..100或null；remainingSeconds为非负整数或null，updatedAt为完整时间。未知时显示不定进度和正在估算；预计用时不是完成保证，不能客户端倒数到零就设completed。只有服务端确认简报发布后返回completed/partial和briefId。刷新通过当前账户恢复活动生成，失败/封禁/429有明确状态，不泄露技术过程。

封禁/配额不删除既有简报或偏好。清Cookie创建的是新身份，同IP创建速率与资源门槛仍生效；这不是保证识别真实自然人。IP在受信反向代理边界提取，统计页面只展示脱敏标签。

## 持久化与文件访问边界

MySQL 唯一约束至少覆盖偏好版本、配置版本、每日业务键、幂等键、thread 消息序号和 run 事件序号；短事务登记 run/outbox，网络与模型调用不持有事务锁。不可变来源快照在关联运行可回放期限内保留。

Agent 只见 `/rss` 的本次只读快照和 `/workspace` 的本次运行目录；inputs 只读，output 可写。文件服务拒绝父路径、宿主路径及解析后越界访问；read 保存全文件 hash，write 在受控排他区间比较最新 hash 并原子替换。创建必须显式且父目录合法；冲突要求重新读取。bash 的持久挂载只读，持久写回走同一 CAS 服务。

## 正式 DTO 与固定评估输入

NewsItem的fetchedAt记录实际取得证据的时刻，snapshotId关联不可变原始来源或搜索证据。公开Brief的missingSources说明部分完成所缺的来源。Source的snapshotFetchedAt是当前有效快照的数据取得时刻，lastFetchedAt是最近HTTP尝试时刻，cacheAgeSeconds和stale表达缓存状态；失败或304不创建虚假的新快照。NewsNow的upstreamRevision保存周期配置依据，不能将本地轮询周期当上游真实周期。

RunEvent.time使用完整RFC 3339时间；AgentRun的inputTokens/outputTokens/cost允许null且只从真实用量与已配置价格计算。界面的短时间和模拟数值不直接持久化。/me/generations/current按当前Cookie身份查询最近一次生成（含终态），用于在无本地generationId时恢复公开进度。

EvalCase每次保存生成新revision，固定preferenceSnapshot、fixedAt及sourceSnapshotIds。创建时未提供固定字段便捕获当前可用来源和时钟，偏好描述作为背景并保留空话题/关键词的version=0快照；这是评估文本输入，不是用户保存无效偏好的豁免。编辑省略固定字段保持原值。显式空来源集合表示无证据测试，实验不得悄悄联网补充。

EvaluationRun在创建事务中复制用例修订与固定输入清单，并生成datasetVersion，绑定配置/模型及scorerVersion。后续用例或配置修改不改变已启动实验。results记录逐用例的状态和评分；每项有metric、method(rule/human/llm)、value、maximum、passed、error。不可用评分保持null，运行失败不冒充不相关；所有聚合明确评分来源且只纳入可用样本。空用例集拒绝创建实验，无样本不显示准确率。评估的产物与正式发布隔离。

原型检查器对synthetic页面数据的正式DTO投影仅用于检查交换边界；后端必须独立生成上述事实并按AC验证，不得复用投影制造采集、用量或评分证据。
