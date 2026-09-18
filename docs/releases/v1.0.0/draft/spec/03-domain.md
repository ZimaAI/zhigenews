# 领域模型与数据边界（ITERATE 草稿）

本稿对应 v1.0.0 第一轮原型，尚未冻结。权威交换格式见 `../contracts/openapi.json`；页面上的模拟运行、评分与投递不代表下列后端不变量已实现。

## 四类模型

| 层次 | 对象与职责 | 不应混入的内容 |
| --- | --- | --- |
| 领域 | 用户、偏好版本、来源/快照、运行/子任务、简报版本、投递尝试、配置版本、记忆、评估实验 | 组件是否展开、表单脏状态、toast |
| 交换 | 同名 Preferences/NewsItem/Brief/AgentRun 等 DTO，写请求、分页、错误、SSE | ORM 对象、密钥原文、宿主物理路径、模型私有思维链 |
| 页面 | DemoState、Scenario、筛选/页码、编辑草稿、loading/error、read 展示与对比选项 | 不承担权限、调度、投递保证 |
| 持久化 | MySQL 主外键/唯一约束/版本、不可变文件快照、checkpoint、outbox 与事件日志 | 不解析格式化的页面时间作为调度依据 |

## 实体、关系与不变量

| 领域实体 | 身份与关系 | 主要不变量/交换映射 |
| --- | --- | --- |
| User / Session | User 有稳定 ID；Session 归属一个 User | 角色 user/admin；禁用与注销能撤销有效会话；`Preferences.role` 是职业背景而非授权角色 |
| PreferenceRevision | `(userId, version)` 唯一 | 保存创建新版本；排除优先于包含；required 至少命中一个关键词；旧运行保留原快照；对应 Preferences |
| DeliveryPlan | 每用户一个计划 | 本地 HH:mm + IANA 时区，渠道设置与目的地验证分开；修改邮箱使 verified 失效；对应 DeliverySettings |
| Source / SourceSnapshot | Source 稳定 ID；一个源有多次 Fetch 和不可变 Snapshot | NewsNow 与 RSS 分开；周期单位秒；成功发布新快照才能更新 lastSuccess；坏响应不覆盖有效快照；对应 Source |
| NewsEvidence / BriefItem | 条目带原 URL、来源及引用；BriefItem 归属某一期版本 | 来源发布时间可空，不能拿抓取/榜单时间替代；原文证据与 Agent 推荐理由分开；read 是用户条目阅读状态；对应 NewsItem/Citation |
| AgentConfigRevision / ModelEndpoint | 配置草稿发布成不可变版本并引用模型 | 模型 ID、端点、能力、密钥引用分离；API key 只写/加密保存；新运行绑定快照；对应 AgentConfig/ModelConfig |
| AgentRun / Subtask | run 归属用户与 thread；子 run 归属父 run | 绑定偏好/配置/来源快照；预算包括子任务；运行取消独立于未来计划；对应 AgentRun/Subtask |
| MessageJournal / Summary | `(threadId,messageSeq)` 单调唯一；调用实例关联 toolCallId | 原始日志保留，修复重建模型视图不重新编号；摘要另存覆盖范围与版本；最新用户原文不压缩 |
| BriefRevision | 简报归属用户与 run；日期内可有多个 version | 内容一经发布不可覆盖，引用及偏好快照可追溯；部分完成仍说明缺失来源；对应 Brief |
| DeliveryAttempt | 归属精确 briefId/版本与渠道 | 生成完成不意味着发送成功；重试复用同一简报，尝试次数递增；目的地只显示脱敏值；对应 Delivery |
| UserMemory | 归属用户 namespace，带来源/更新时间 | 显式偏好高于推断；网上内容不可当用户事实；删除仅影响后续读取；对应 Memory |
| EvaluationDataset / EvaluationRun | 固定 case/来源快照与时钟；实验绑定配置与评分器版本 | 无评分为 null，非 0；规则/人工/LLM 分开；没有样本不显示准确率；对应 EvalCase/Evaluation |

## 状态与动作

运行通常为 `queued → running → completed/partial/failed`。取消为 `queued/running → cancelling → cancelled`，只有 worker 确认才显示已取消；终态不会因 SSE 断线改变。恢复在同一逻辑 run/thread 的 checkpoint 上继续，不能偷偷新建一次有副作用的工具执行。工具错误可被 Agent 处理后继续，单个失败事件不必等于整个 run 失败。

Source 使用 `unverified/healthy/syncing/failed/disabled`；发起采集只代表 syncing，解析并发布有效快照才 healthy。失败保留上一成功快照及其时间。Source 的 lastChanged 是本地检测到内容变化的时间，不是上游真实刷新时间。

配置为 `draft → published`；修改已发布配置应创建新草稿。停用模型不重写已经记录的历史版本，后续创建运行必须检查所引用模型是否仍可用。

投递使用 `disabled/pending/submitted/failed/unknown`。`submitted` 仅表示 SMTP/渠道接受提交；没有回执不能显示“已送达”。超时后无法确定外部是否接受则 unknown；用户明确选择重试时保留这个不确定性。无邮件渠道不影响站内简报可读。

评估使用 `queued/running/completed/failed`；单项评分不可用为 null，不能记 0 或通过。原型的 completed 与分数均为模拟。

## 新简报、重试与暂停

“立即生成/重新生成”是新的用户内容意图，创建新 run 与新 BriefRevision，并绑定当时最新偏好；老简报继续可读。重复点击同一次意图复用幂等键，不生成多个任务。

“重试推送”沿用原 briefId 和内容版本，只增加投递尝试，不再次调用 Agent 生成。修改偏好后重试旧邮件仍发送旧简报；要应用新偏好需明确生成新简报。

暂停只停止未来每日调度，已运行任务有独立取消动作。恢复计算下一次计划，不补发全部遗漏。每日调度业务键包含用户、计划槽位和简报类型；队列至少一次投递，通过唯一约束和 outbox 避免重复创建业务记录，不承诺 SMTP 外部绝对只发送一次。

## 权限与时间

用户只读写本人的偏好、计划、记忆、简报、阅读标记和运行；管理员读管理视图与脱敏运行详情、管理来源/模型/配置/用户状态。服务端解析当前身份，不接收客户端声称的 userId 作为归属依据；用户作用域跨账号 ID 返回不可见。

数据库时间为 UTC；ISO 时间表示实际事件时刻，日期与每日 HH:mm 按用户 IANA 时区解释。夏令时不存在的时刻调整到首个有效时刻，重复时刻执行一次。原型固定时钟 `2026-09-18T08:12:00+08:00`，格式化 nextRunAt 和事件短时间是页面投影，不可直接持久化为调度事实。

新闻发布时间、采集成功时间、快照发布时间、简报生成时间、计划槽位和渠道提交时间分别记录；未知来源发布时间保留 null。严格新鲜度条件不能通过本地抓取时间补成“新新闻”。来源/运行工作区 ID 由服务端生成，不用外部标题或 URL 拼接目录。

## 持久化与文件访问边界

MySQL 唯一约束至少覆盖偏好版本、配置版本、每日业务键、幂等键、thread 消息序号和 run 事件序号；短事务登记 run/outbox，网络与模型调用不持有事务锁。不可变来源快照在关联运行可回放期限内保留。

Agent 只见 `/rss` 的本次只读快照和 `/workspace` 的本次运行目录；inputs 只读，output 可写。文件服务拒绝父路径、宿主路径及解析后越界访问；read 保存全文件 hash，write 在受控排他区间比较最新 hash 并原子替换。创建必须显式且父目录合法；冲突要求重新读取。bash 的持久挂载只读，持久写回走同一 CAS 服务。

正式 DTO 尚待补足采集时间/快照引用、可空真实用量、完整 SSE 时间与评估评分来源，见契约 README 的冻结前清单。领域规则不以原型暂缺字段为由取消；下一轮调整需同步原型、schema、样例与验收。
