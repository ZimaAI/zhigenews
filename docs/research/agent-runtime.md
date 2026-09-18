# AI 新闻简报 Agent：运行时调研与建议

调研日期：2026-09-18。阶段：DISCOVER。本文是供原型、领域模型和后续规范使用的研究输入，不是已批准的实现规范，也不代表依赖、数据库或 Agent 已经运行验证。

研究中的字段和路径属于机制示例，合并后的产品行为和目录命名以 [v1.0.0 架构草案](../releases/v1.0.0/draft/spec/04-architecture.md) 为准。

## 1. 结论

建议采用 **LangChain `create_agent` 组装自主工具循环，LangGraph 承担状态与恢复，本项目自建新闻 Harness**。借鉴 Deep Agents 的文件系统、子 Agent、上下文卸载、工具调用修复模式，但不直接把它的默认行为当成本系统需求已经满足。用户要求的消息排序修复、摘要独立存储、保留最新用户输入、文件哈希冲突保护，都需要本项目明确实现。

建议业务数据、运行记录、检查点和长期记忆继续使用 MySQL；存在可评估的社区 MySQL Checkpointer/Store，不能因为官方示例使用 PostgreSQL 就改变用户指定的数据库。

最先需要在原型和规范中表达的运行行为是：订阅快照 → 读取本地新闻索引/RSS → 按需 Tavily 搜索 → 选题与去重 → 编写带来源的简报 → 校验 → 保存与推送。内部分析允许 Agent 自主决定工具调用顺序；投递和任务幂等性由业务服务控制。

## 2. 查证范围和固定版本锚点

本次访问了官方文档、官方源码和 MySQL 适配器维护者源码。以下 commit 通过 GitHub API 查询后，继续读取了对应 raw 文件，避免只依赖会变化的主分支网页。

| 项目 | 本次查阅 commit | 本次用途 |
| --- | --- | --- |
| langchain-ai/langchain | `fd4f1615359371fbb1b3b2de9183a18a15ee9e34` | `create_agent`、基类摘要中间件 |
| langchain-ai/deepagents | `9b515ef09a37a02034ef7384701bbcbbc91a122e` | 消息修复、摘要事件、模型请求渲染 |
| langchain-ai/langgraph | `c81c13533ee48c1ae0ef2de314737ef0c455f2be` | 消息 reducer、检查点接口 |
| tjni/langgraph-checkpoint-mysql | `16c87be69f4d62d4b933ac13dbd8afc2ef226b32` | MySQL Checkpointer、Store、依赖约束 |

这些是研究锚点，不是建议直接安装主分支。后端实施时应选择正式发布包并生成 lockfile，再对实际安装版本执行兼容验证。

## 3. 已验证事实与本系统的设计区别

### 3.1 `create_agent` 可以满足 Agent Loop 的基础要求

**已验证事实：**官方将 Agent 描述为模型与工具循环；`create_agent` 接受模型实例/标识、工具、系统提示词、中间件、`state_schema`、`context_schema`、`checkpointer`、`store` 和结构化输出配置。返回的运行图能够执行、流式输出和恢复。源码签名与文档一致。[Agents 文档](https://docs.langchain.com/oss/python/langchain/agents)、[factory.py 固定源码](https://github.com/langchain-ai/langchain/blob/fd4f1615359371fbb1b3b2de9183a18a15ee9e34/libs/langchain_v1/langchain/agents/factory.py#L840)

**建议：**主 Agent、研究子 Agent、校验子 Agent 都使用同一个 Harness 工厂，模型、工具集和系统提示词按角色配置。不要把六个工具机械串成固定链；应让模型根据用户偏好和已找到的证据决定下一步，同时由运行预算限制循环。

Gateway 只进行鉴权、输入校验、发起任务、读取结果和事件流。Harness 处理模型装配、工具、记忆、中间件和子 Agent。新闻轮询、定时触发、持久化、投递是应用服务；不要求 LLM 自己判断是否到了每日推送时间。

### 3.2 State、Context、长期记忆是不同的存储职责

**已验证事实：**`ToolRuntime` 提供当前状态、不可变调用上下文、Store、工具调用 ID、流式写入器等；该参数由运行时注入，不出现在发给模型的工具参数 schema。工具可以用 `Command` 更新 state，并带上对应 `ToolMessage`；并行工具更新同一字段需要 reducer。[Tools 文档](https://docs.langchain.com/oss/python/langchain/tools)

**建议字段：**

| 层次 | 本系统建议内容 | 约束 |
| --- | --- | --- |
| `NewsAgentState` | `messages`、`summary`、`summary_revision`、候选新闻 ID、证据索引、已选新闻、产物、工具预算计数、子任务状态 | 可恢复的可序列化状态，不放数据库连接或明文密钥 |
| `RunContext` | `user_id`、`run_id`、订阅版本、模型/提示词/Agent 配置版本、来源快照、时间窗、沙箱句柄引用 | Gateway/Worker 注入，模型不能通过工具参数冒充另一用户 |
| Runnable config | `thread_id`、递归上限、回调、追踪标签 | 一个运行的稳定身份；恢复时保持同一线程 |
| MySQL 长期记忆 | 用户明确偏好、喜欢/不喜欢的反馈、已推送新闻、去重历史 | 按用户 namespace 查询，跨每日运行复用 |
| 审计事件表 | 原始模型/工具消息、顺序号、修复事件、摘要事件、子任务关联 | 保存事实顺序，和发给模型的重建列表分开 |

正式偏好表是用户配置的权威数据；长期记忆中的推断不能静默覆盖用户显式配置。原型可以展示“来自订阅配置”和“来自反馈”的不同来源。

**已验证事实：**LangGraph Store 用 namespace 和 key 组织跨线程数据，Checkpointer 负责线程内状态；两者不是同一个概念。[Long-term memory 文档](https://docs.langchain.com/oss/python/langchain/long-term-memory)、[Stores 文档](https://docs.langchain.com/oss/python/langgraph/stores)

### 3.3 自增消息 ID 不能直接假设由 LangChain 提供

**已验证事实：**`add_messages` 按消息 ID 合并，同 ID 会替换；缺少 ID 时会生成 UUID；它支持 `RemoveMessage(id=REMOVE_ALL_MESSAGES)` 清空后重建。因此“每条消息自动具有自增 ID”是本系统需要实现的业务约束，不是框架保证。[message.py 固定源码](https://github.com/langchain-ai/langgraph/blob/c81c13533ee48c1ae0ef2de314737ef0c455f2be/libs/langgraph/langgraph/graph/message.py#L61)

**建议：**MySQL 中记录自增 `message_event_id` 和线程内单调 `sequence`；LangChain 消息保留稳定字符串 `id`，并建立对应关系。工具调用的 `tool_call_id` 是第三种身份：只能用它关联模型请求与工具结果，不能用消息 ID 替代。重建输入顺序后，不修改原始事件自增 ID 来伪造发生顺序。

## 4. 工具消息修复：需要实现的完整语义

**已验证事实：**Deep Agents 的 `PatchToolCallsMiddleware.before_agent` 先建立已回答调用 ID 集合，再给没有结果的合法/无效工具调用补 `ToolMessage(status="error")`。它明确表示结果未记录，可能取消或中断，而不声称动作一定没发生。当前源码不会把已经存在但错位的工具结果重新放到对应 AI 消息之后。[patch_tool_calls.py 固定源码](https://github.com/langchain-ai/deepagents/blob/9b515ef09a37a02034ef7384701bbcbbc91a122e/libs/deepagents/deepagents/middleware/patch_tool_calls.py)

**本系统建议算法：**

1. 从已经完成流式聚合的消息建立 `tool_call_id -> ToolMessage` 索引。保留原始消息和修复审计记录。
2. 顺序扫描模型消息、真实用户消息等非工具消息，保持它们的相对顺序。
3. 对每条 AI 消息，按它声明的工具调用顺序取出对应工具结果，紧跟在该 AI 消息后面。一个 AI 消息可以有多个工具调用，应恰好有每个调用的终态结果；普通无工具调用的 AI 消息无需工具结果。
4. 对缺失结果补一个明确的中断/结果未知错误，而不是伪造成功。对孤立结果不发给模型，转入诊断记录。
5. 同一个调用 ID 的重复结果应按明确规则收敛为一个终态；同一个 ID 被不同 AI 请求重复使用是歧义，应终止该输入的自动修复并报告数据错误。
6. 用 `REMOVE_ALL_MESSAGES` 加重建列表更新 `messages`。仅返回重排列表会被 `add_messages` 按 ID 合并，不能保证达到整体重排的目的。

复杂度可以做到 O(消息数 + 工具调用数)，无需为每个工具调用重复扫描消息列表。

修复时机是恢复入口，以及每次模型请求前的协议校验；**不能在 AI 刚派发工具、工具尚在运行时补“中断”结果**。取消时先确认工具任务已终止/完成并登记终态，再修复下一次输入。若某工具有写入副作用但丢失回执，应先核对工具执行记录，不自动重复执行。

建议测试样例：单缺失、多并行调用部分缺失、错位结果、孤立结果、重复结果、非法工具参数、取消后恢复、连续修复两次结果相同。修复后验证调用 ID 一一对应与相邻关系，同时验证非工具消息相对顺序不变。

## 5. 摘要压缩：必须保留用户原文并分离渲染

### 5.1 基类能提供什么，不能假设什么

**已验证事实：**LangChain `SummarizationMiddleware` 支持消息数、绝对 token、输入比例触发；列表条件为 OR，同一条件字典内为 AND；比例需要模型 profile；默认 `keep` 为最近 20 条，摘要输入默认裁到 4000 token。基类在 `before_model` 摘要后清空旧列表，再加入一条标记 `lc_source="summarization"` 的 `HumanMessage` 与保留消息。[Prebuilt middleware 文档](https://docs.langchain.com/oss/python/langchain/middleware/built-in)、[summarization.py 固定源码](https://github.com/langchain-ai/langchain/blob/fd4f1615359371fbb1b3b2de9183a18a15ee9e34/libs/langchain_v1/langchain/agents/middleware/summarization.py#L398)

**源码核对后的差异：**

- 安全切点照顾 AI/Tool 组，但并不把最新真实用户输入作为永远保留的锚点。一个用户输入后发生很多工具循环时，该输入仍可能落到摘要区。
- `_trim_messages_for_summary` 使用 `strategy="last"`、`start_on="human"`。裁后没有 HumanMessage 时可能得到空列表；当前生成逻辑会返回占位字符串，不执行真实摘要。
- 基类默认对 `state["messages"]` 计数。若摘要被移到独立字段，就必须主动把它加回 token 预算；系统提示词、工具定义、长期记忆渲染也应计入完整请求预算。
- 基类的 `self.model` 是摘要模型；主模型和摘要模型不同，不能直接把摘要模型的 profile 当主模型容量。

以上均由同一固定版本源码的 `before_model`、`_get_profile_limits`、`_build_new_messages`、`_find_safe_cutoff_point`、`_trim_messages_for_summary` 核对得出；属于实现阶段必须覆盖的差异，不是仅配置 `keep=20` 就完成需求。

### 5.2 本系统建议分为两个中间件

**`NewsSummarizationMiddleware(SummarizationMiddleware)`：**

1. 同时覆盖同步与异步入口，避免 FastAPI/Worker 使用 `ainvoke` 时绕过自定义实现。
2. 用消息来源标记定位最新真实用户输入；排除 `lc_source="summarization"` 的框架摘要。保留原 `id`、内容和附件引用。
3. 先完成工具消息修复，再按完整 AI/Tool 组选择早期消息。将最新用户原文从待压缩段中摘出；即便长工具循环造成这条用户消息位于保留窗口之外，也必须留下它。
4. 摘要输入是“现有摘要 + 本轮新纳入压缩的历史”，不单独摘要新增历史后丢弃旧摘要。新闻摘要应保留目标偏好、已检索来源、候选/排除理由、引用 ID、已产物路径、未完成步骤、工具异常与文件版本。
5. 压缩成功后更新独立 `summary`、`summary_revision`、压缩边界信息；重建 `messages`，在保留的后续消息前放回刚才提取的用户原文，且不重复插入已经在保留段中的用户消息。
6. 摘要失败时不提交新摘要、不删除原文，记录可重试失败。摘要输入超过摘要模型窗口时按完整消息组分批滚动压缩，避免默认的 4000 token 裁剪静默丢证据。

**`SummaryContextMiddleware`：**仅在 `wrap_model_call`/`awrap_model_call` 中读取独立摘要并用 `request.override(...)` 构造本次模型输入；不再次持久化一份合成 HumanMessage，不负责摘要生成。给摘要标注它是历史信息，不把新闻文本中的指令升级为系统规则。

**预算建议：**分别维护主模型输入预算和摘要模型输入预算。主模型预算包含系统提示、工具 schema、摘要、长期记忆、最新用户输入、保留消息，并预留输出和计数误差空间。优先使用实际 tokenizer；近似计数在中文新闻上需要真实调用校准。若仅用户原文/工具定义就超限，应给出可解释错误，不能为了达到阈值把必须保留的用户输入再次压缩。

继承基类符合用户要求，但若复用 `_determine_cutoff_index` 等下划线方法，需锁定 LangChain 版本并做兼容测试。这些内部方法不是稳定公共扩展契约。

### 5.3 Deep Agents 可借鉴的部分

**已验证事实：**当前 Deep Agents 摘要实现使用独立 `_summarization_event`（包含切点与摘要消息）重建有效上下文，在 `wrap_model_call` 里合并摘要和尾部消息，预算计算还接收系统消息与工具定义；旧记录可卸载到 backend。它目前通过组合一个 LangChain 摘要 helper 工作，而不是满足本项目“继承基类且另设渲染中间件”的结构。[Deep Agents summarization.py 固定源码](https://github.com/langchain-ai/deepagents/blob/9b515ef09a37a02034ef7384701bbcbbc91a122e/libs/deepagents/deepagents/middleware/summarization.py#L1472)

建议借鉴其“完整历史用于审计、有效上下文用于模型”的分离，但本项目以消息 ID/sequence 保存压缩边界，避免在消息重排后继续使用过期数组下标。

## 6. 文件工具与 shell 必须共享访问边界

**已验证事实：**Deep Agents 文档明确：`FilesystemBackend(root_dir=..., virtual_mode=True)` 提供路径限制；`virtual_mode=False` 不构成访问限制。`LocalShellBackend` 在宿主机执行 shell，工作目录不是安全边界，启用 `virtual_mode` 也不能限制 shell 任意路径访问。生产多租户应用应使用真正隔离的 sandbox backend。[Backends 文档](https://docs.langchain.com/oss/python/deepagents/backends)、[Sandboxes 文档](https://docs.langchain.com/oss/python/deepagents/sandboxes)

**本系统建议：**

| 工具 | 对模型的主要入参 | 必须有的输出/行为 |
| --- | --- | --- |
| `list_dir` | 虚拟路径、分页/上限 | 仅虚拟路径、类型、分页游标；限制条数 |
| `read_file` | 虚拟路径、起止行 | 行号、整文件 SHA-256、截断标记、下一段；限制字节/行数 |
| `search_content` | 根虚拟路径、关键词、上限 | 匹配虚拟路径、行号、短片段；限制文件数、结果数和总输出 |
| `write_file` | 虚拟路径、内容、期望哈希/新建模式 | 成功后的新哈希；冲突要求重读 |
| `bash` | 命令、虚拟工作目录、超时 | 容器内执行，限制资源与输出，不直接写受版本保护的文件 |
| `web_search` | 查询、新闻时间窗、来源约束、上限 | Tavily 结果结构化、来源 URL、标题、时间/缺失标记、限长摘录 |

文件命名空间建议为 `/rss`（只读的已授权 RSS 数据）和 `/workspace`（当前用户本次运行）。NewsNow 缓存可在运行启动时导出成 `/workspace/input/newsnow.jsonl` 只读输入，既满足三类来源，又不额外开放后端缓存目录。系统预先创建工作目录及 `input/`、`output/`；`write_file` 可新建文件，但父目录不存在时按用户要求报错。

路径处理拒绝原始路径中的 `..` 段、宿主机盘符/UNC、空字节和不支持的路径表达；按虚拟根映射后再次做真实路径归属判断。符号链接、junction 和写入时的父目录解析必须同样检查。不能用字符串 `startswith` 判断根目录包含关系。

SHA-256 必须覆盖整个文件，不只是返回给模型的片段。读取后记录哈希；写入在锁内比较当前哈希，通过后临时文件写入并原子替换，再记录新哈希。新建使用“必须不存在”语义；两个并发写入者只能有一个成功。只在写之前无锁比较一次，会留下比较与替换间的竞争窗口。文件版本账本应按运行隔离且由服务端维护；哈希作为工具输出便于模型理解，但不依靠模型自己声称读过文件。

**需要明确的产品行为：**给 shell 可写挂载会绕过 `write_file` 的哈希检查。建议首版 `bash` 只读访问 RSS 和已存在的工作区数据，临时计算使用容器临时目录；正式新闻文件统一由 `write_file` 提交。若未来需要 shell 直接生成文件，可使用隔离 staging 后由同一哈希写入服务提交差异，不能直连宿主工作区绕过并发保护。该建议保留 shell 计算能力和文件写入能力，约束的是写入通道。

Linux 容器只挂载被授权的数据根；搜索通过 Harness 中的 Tavily 工具调用，不把模型、数据库或 Tavily 密钥暴露给 shell。容器镜像自带运行时文件不等于开放宿主机目录。此方案是设计建议，当前未创建或验证任何 sandbox。

## 7. MySQL 检查点与长期记忆

### 7.1 社区实现存在，但兼容性要实测

**已验证事实：**`tjni/langgraph-checkpoint-mysql` 提供 `PyMySQLSaver`、`AIOMySQLSaver`、`AsyncMySaver`；仓库包含 MySQL Store 和测试。README 要求 MySQL >= 8.0.19 / MariaDB >= 10.7.1，首次要运行 `.setup()`；显式创建连接时需要 `autocommit=True`。它提示 MySQL >= 9.6 的 MD5 生成列变更尚未提供迁移路线。[维护者仓库 README](https://github.com/tjni/langgraph-checkpoint-mysql)

固定源码的 `pyproject.toml` 版本为 3.0.0，要求 `langgraph-checkpoint>=2.1.2`，但没有上界；开发依赖把 LangGraph 指向一个旧 commit。这只能证明存在依赖声明，不能证明它兼容今天的所有 LangGraph 新特性。[pyproject.toml](https://github.com/tjni/langgraph-checkpoint-mysql/blob/16c87be69f4d62d4b933ac13dbd8afc2ef226b32/pyproject.toml)

`BaseAsyncMySQLSaver` 实现 `aget_tuple`、`alist`、`aput`、`aput_writes`、`adelete_thread`。Store 提供 namespace/key 的 JSON 保存、筛选和分页；其查询构造并没有执行 embedding 相似度排序，不能把 Store 的 `search` 直接宣传为语义检索。[aio_base.py](https://github.com/tjni/langgraph-checkpoint-mysql/blob/16c87be69f4d62d4b933ac13dbd8afc2ef226b32/langgraph/checkpoint/mysql/aio_base.py)、[Store base.py](https://github.com/tjni/langgraph-checkpoint-mysql/blob/16c87be69f4d62d4b933ac13dbd8afc2ef226b32/langgraph/store/mysql/base.py)

**建议选择：**以 MySQL 8.4 LTS 作为部署候选，优先验证上述异步实现；长期记忆第一版用用户 namespace + 结构化查询，足以存偏好和已读历史，不因此新增向量数据库。[MySQL 8.4 发布策略](https://dev.mysql.com/doc/refman/8.4/en/mysql-releases.html)

### 7.2 验证与自定义适配器的退出条件

**已验证事实：**`BaseCheckpointSaver` 契约涉及 checkpoint、channel versions、父 checkpoint 和 pending writes；不是把 `messages` 序列化为一个 JSON 字段。官方提供 `langgraph-checkpoint-conformance` 验证基础方法及扩展能力。[BaseCheckpointSaver 固定源码](https://github.com/langchain-ai/langgraph/blob/c81c13533ee48c1ae0ef2de314737ef0c455f2be/libs/checkpoint/langgraph/checkpoint/base/__init__.py#L177)、[Checkpointers 文档](https://docs.langchain.com/oss/python/langgraph/checkpointers)

后端实施的兼容门槛建议为：锁定 Python/LangChain/LangGraph/checkpoint/MySQL driver 版本；对真实 MySQL 运行官方 conformance 的基础测试；再验证工具执行中取消与恢复、并行节点 pending writes、父子 checkpoint namespace、同线程并发控制、历史读取、序列化、删除和进程重启恢复。当前阶段只记录门槛，不把它作为阻止 DISCOVER 交付的前置条件。

优先使用普通 `AgentState.messages` + `add_messages`。Deep Agents 当前默认使用 beta `DeltaChannel` 优化检查点规模，其 reducer 与 `REMOVE_ALL_MESSAGES` 语义并不完全相同；在 MySQL adapter 和本项目重建逻辑未经验证前，不复制这个优化。

若社区包在锁定版本下无法通过核心恢复测试，再考虑基于 `BaseCheckpointSaver` 实现本项目 MySQL adapter：实现同步/异步契约、typed serializer、版本与 pending writes 的原子性、namespace 隔离、历史顺序和删除。自建持久层的风险是“正常运行通过，故障恢复丢状态”，不能仅用一次写入/读取冒烟验收。无论选社区包还是自建，都不默认引入 PostgreSQL。

## 8. 子 Agent、观测和评估

**已验证事实：**Deep Agents 支持专门子 Agent，以及用已编译 LangGraph/`create_agent` 图构建的 `CompiledSubAgent`；隔离模式是把专门任务交给独立上下文，再返回结果。结构化子 Agent 输出和命名有助于父 Agent 接收结果与观测。[Subagents 文档](https://docs.langchain.com/oss/python/deepagents/subagents)

**建议首版只设两个可选专业角色：**研究子 Agent 接受某个主题和检索限制，返回新闻候选/证据；校验子 Agent 核对被选条目的来源、时间、偏好匹配和重复，返回结构化缺陷。总编 Agent 决定是否调用、汇总和写稿。子任务记录 `parent_run_id`、`subtask_id`、角色、状态、预算和证据。优先独立上下文；共享文件写入仍经过同一个文件服务；总运行预算覆盖子任务，不能通过派生子 Agent 无限扩大调用量。

**已验证事实：**LangGraph 支持 `updates`、`messages`、`custom`、任务/检查点相关流模式，子图流可以携带 namespace；这些是 UI 事件流的基础。[Streaming 文档](https://docs.langchain.com/oss/python/langgraph/streaming)

**建议观测模型：**MySQL 持久化本系统 `agent_runs`、`run_events`、`tool_executions`、`model_calls`、`summary_events`、`evaluation_runs`；Gateway 通过 SSE 提供管理员时间线。展示模型/配置版本、输入来源、工具参数摘要、耗时、调用状态、token 与成本、摘要前后 token、缺失工具修复数量、文件冲突、子任务和最终产物。记录公开的模型响应与工具轨迹，不把“自主思考”解释成必须取得模型的隐式思维链。

LangSmith 的运行/追踪模型和离线/在线评估方法可作为参考；核心管理员观测页面依然属于本系统，不以用户另外购买某个服务为完成条件。可选 exporter 将脱敏 trace 发往 LangSmith。[Observability concepts](https://docs.langchain.com/langsmith/observability-concepts)、[Evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)

**本系统建议的评估维度：**

| 维度 | 方法 | 管理员调优用途 |
| --- | --- | --- |
| 偏好匹配 | 固定订阅样本 + 人工标签；必要时版本化 LLM judge | 比较提示词/模型在同一输入上的筛选表现 |
| 来源可追溯 | 每条简报项必须关联新闻 ID 与 URL，校验引用存在 | 排查无来源结论 |
| 新鲜度 | 基于时间窗的确定性检查；区分发布时间与抓取时间 | 排查旧闻冒充新消息 |
| 重复率 | URL/内容指纹/事件分组，结合已推送历史 | 控制同一新闻多源重复 |
| 摘要忠实度 | 新闻原文与摘要对照、人工抽样/LLM judge | 排查夸大、遗漏限定条件 |
| 工具正确性 | 路径/权限、消息配对、哈希冲突的确定性测试 | 运行时回归测试 |
| 成本与延迟 | 相同来源快照重复评测，采集模型/工具用量 | 比较配置变更的实际代价 |
| 可恢复性 | 中断点注入后恢复，同一投递不重复 | 验证上线后的任务可靠性 |

评估样本、来源快照、提示词和配置版本都要可追溯；LLM judge 得分要展示评估模型和规则，不能作为无解释的绝对真值。后端必须有真实运行和评估记录，不能只有漂亮的监测模拟数据。

## 9. 中间件装配与运行建议

**已验证事实：**前置 hook 按列表正序执行，后置 hook 逆序执行，wrap hook 嵌套包裹；修改顺序会改变运行行为。[Custom middleware 文档](https://docs.langchain.com/oss/python/langchain/middleware/custom#execution-order)

建议在规范里按职责定义装配，而非只列中间件名字：恢复/消息修复 → 摘要压缩 → 本次上下文渲染 → 最终请求预算检查 → 模型调用与受限重试 → 工具调用与工具事件。调用日志要区分一次逻辑调用和多次重试。对模型和搜索的暂时故障可以限次重试；写文件、投递等动作应基于执行 ID/哈希判定是否已完成，不能盲目套通用重试。

管理员应能配置主模型、摘要模型、评估模型、provider/endpoint、密钥引用、温度/输出上限、系统提示版本、循环/工具/时间/费用预算、摘要阈值、子 Agent 并发及工具上限。每次运行冻结配置快照；管理员运行中修改配置只影响后续新运行，防止同一次简报不可重现。

模型 endpoint 不是“填一个 URL 就一定兼容”。实施时至少验证工具调用、并行调用、usage 返回、流式增量、结构化输出、上下文 profile；能力不可用时明确降级或报配置错误。API key 由模型客户端服务端使用，前端仅回显遮罩及密钥版本引用。

## 10. 进入正式后端实现前应冻结的少量决策

这些决策可以在 ITERATE 原型中展示默认方案并确认，无需在 DISCOVER 一次询问全部参数。

1. 每日推送各自新建线程和工作目录，长期偏好/已推送历史跨线程复用。运行消息支持真实用户指令与模型/工具消息；独立聊天产品页面尚未纳入本轮首版范围。
2. 用户看到失败、延迟、部分来源不可用、没有足够匹配新闻时的明确状态；不为凑条数生成无证据新闻。
3. 取消仅停止后续生成，工具是否已经完成按运行记录判定；已投递的简报不会因“取消生成”被假装撤回。
4. bash 读受控数据并计算，正式产物通过统一哈希写入工具保存。
5. 观测默认落到本地 MySQL；外部 trace 平台可选。
6. MySQL adapter、摘要继承与消息重排在后端阶段以锁定版本实测后定稿，保留明确的兼容退出方案。

本次未安装 LangChain/Deep Agents，未调用真实新闻模型，未执行数据库迁移、沙箱或恢复测试；以上“已验证事实”指官方文档和固定源码语义核对，实际运行兼容性仍需在后端阶段验证。
