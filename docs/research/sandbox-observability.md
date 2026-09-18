# Agent 沙箱与监测评估调研

调研日期：2026-09-18。本文是用于原型、领域模型和后续实施规范的研究建议，尚未实现或通过运行验证。引用均为本轮实际访问的官方文档或项目源码；`main` 分支会变化，正式实施须固定依赖版本与镜像摘要。

本文的目录和预算为候选示例；本轮合并方案使用 [架构草案](../releases/v1.0.0/draft/spec/04-architecture.md) 的 `inputs/`、`output/` 目录，产品默认值见 [评审入口](../releases/v1.0.0/draft/DISCOVERY.md)。后续收藏、私有 RSS 等示例不自动扩张首版范围。

## 1. 结论与参考实现

本系统适合采用“虚拟文件服务 + 独立命令容器 + Harness 事件记录”三个部分。虚拟文件服务执行路径权限、读取预算和文件哈希校验；命令容器负责隔离任意 shell；Harness 负责模型、Tavily 和数据库操作。模型密钥、Tavily 密钥、数据库连接串都保留在 Harness 服务端。

| 已核实的开源设计 | 本系统采用的部分 | 不直接照搬的部分 |
| --- | --- | --- |
| DeepAgents `CompositeBackend` 将不同虚拟路径路由到不同后端；文件工具与命令执行能力分开 | `/rss` 只读、`/workspace` 按用户和运行隔离；统一后端接口 | 本系统继续使用用户指定的 `langchain.agents.create_agent`，无需把 Agent 入口替换为 `create_deep_agent` |
| DeepAgents `FilesystemBackend` 有虚拟路径模式；`LocalShellBackend` 在宿主运行命令 | 路径映射、限量读取、工具返回结构 | 官方明确指出 shell 会绕过虚拟路径限制，因此不能将它当作本系统生产沙箱 |
| OpenHands Docker Runtime 使用独立动作执行环境，把命令及结果与 Agent 主进程分开 | Harness 的 `SandboxRunner` 接口与独立容器生命周期 | 新闻系统不需要内嵌浏览器、Jupyter、IDE 或整套 OpenHands 服务 |

以上事实分别来自 [DeepAgents Backends](https://docs.langchain.com/oss/python/deepagents/backends)、[DeepAgents Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes) 和 [OpenHands Runtime Architecture 源文档](https://raw.githubusercontent.com/OpenHands/docs/main/openhands/usage/architecture/runtime.mdx)。这些项目提供架构参考，并不证明本项目实现已经安全。

还核对了 [DeepAgents 文件后端源码](https://raw.githubusercontent.com/langchain-ai/deepagents/main/libs/deepagents/deepagents/backends/filesystem.py)：其文件写入会使用截断写模式，不能直接满足本需求的“读过的哈希与当前哈希一致才覆盖”。CAS 必须由本系统另外实现。

## 2. 文件权限与目录布局

建议物理目录由可信配置和数据库身份构成，绝不接受模型给出的宿主目录。以下是候选布局：

```text
data/
  rss/{source_id}/{YYYY}/{MM}/{DD}/{fetch_id}/
    raw.xml
    normalized.jsonl
    metadata.json
  newsnow/{source_id}/{YYYY}/{MM}/{DD}/{fetch_id}/
    snapshot.json
  runs/{user_id}/{run_id}/
    inputs/newsnow.jsonl
    inputs/sources.json
    drafts/
    artifacts/
```

| Agent 虚拟路径 | 文件工具权限 | 物理范围 |
| --- | --- | --- |
| `/rss/` | 列出、读取、搜索 | 当前运行获准使用的 RSS 快照视图 |
| `/workspace/inputs/` | 列出、读取、搜索 | 本次输入快照，含 NewsNow 候选、来源清单 |
| `/workspace/drafts/` | 列出、读取、搜索、CAS 写入 | 当前用户当前运行的草稿 |
| `/workspace/artifacts/` | 列出、读取、搜索、CAS 写入 | 当前用户当前运行的最终简报与附件 |

`/rss` 映射稳定的快照集合，不把爬虫正在改写的临时文件暴露给 Agent。共享公开 RSS 源可以复用同一不可变物理快照；私有订阅源必须按用户授权过滤。运行输入清单保存 `source_id / fetch_id / content_hash / fetched_at / published_at`，便于查证“当时 Agent 看到了什么”。NewsNow 缓存经只读输入快照交给 Agent，避免遗漏第三类新闻来源，也不必新增一个全局可写根目录。

`user_id`、`run_id` 来自认证和任务调度上下文，工具参数不接受用户身份覆盖。子 Agent 继承父运行权限，默认使用各自草稿文件名；不能获得另一个用户的工作目录。长期记忆放在受身份校验的数据访问层，不能将全用户记忆表或数据库文件挂进沙箱。

### 路径解析规则

1. 工具输入只接受以 `/rss/` 或 `/workspace/` 为根的 POSIX 虚拟路径。精确识别路径段，不能用字符串前缀判断包含关系。
2. 在标准化之前拒绝任何 `..` 段、反斜杠、空字节、盘符、UNC、`~` 扩展及非约定根路径。`/workspace2` 不属于 `/workspace`。JSON 工具参数不做 URL 解码，HTTP 层也不能在校验后再次解码。
3. 映射真实路径，解析之后用路径组件判断属于授权根；读取要求目标存在，创建文件要求父目录存在。无权限和不存在分别返回稳定错误码，错误文本只包含虚拟路径。
4. 拒绝符号链接、Windows junction/reparse point 及非普通文件；搜索也不跟随链接。不允许 Agent 创建设备、FIFO、socket 或链接。
5. Linux 正式实现使用根目录文件描述符逐级打开目录，再对最终文件使用 `dir_fd` 与 `O_NOFOLLOW` 等机制；不能只做一次 `Path.resolve()`，随后再以路径字符串打开，从而留下校验与使用之间的竞态。

Python 官方说明 `dir_fd` 能力依平台而异，Windows 不具备同等接口；`os.replace` 的原子重命名也有文件系统边界要求。因此 Windows 的路径检查测试不能替代 Linux 的隔离验收。[Python os 文档](https://docs.python.org/3/library/os.html)

## 3. 哈希防脏写：读版本与条件写入

建议 SHA-256 对**原始文件字节**计算，不对换行已标准化的字符串计算。一次读取即使只返回部分行，也必须记录整个文件的版本；否则未返回部分的修改可能被漏掉。

- `read_file(path, start_line, end_line)`：在受保护的读取过程里取得内容与完整哈希，返回 `content / sha256 / line_range / truncated`，并在可信运行状态保存 `(actor_id, canonical_virtual_path) -> last_read_hash`。
- `write_file(path, content, expected_hash)`：覆盖现有文件必须同时满足“此调用主体确实读过该文件”“参数等于已记录哈希”“当前文件完整哈希仍相同”。哈希由服务端核对，不能只相信模型传来的值。
- 创建新文件显式使用 `create_new=true`；父目录必须已存在，目标文件必须不存在。目标突然出现就返回 `FILE_ALREADY_EXISTS`，不能降级成覆盖。
- 冲突返回 `FILE_CHANGED`，保留现有文件；告诉 Agent 重新读取后重试。成功写入返回新哈希，并更新此主体的版本记录。
- 将“取锁 → 重新验证路径 → 读取当前哈希 → 比较 → 写同目录临时文件 → 原子替换”放进同一个临界区。仅“先比较、稍后写入”仍有竞态；原子替换本身也不等于 CAS。
- 初版由每次运行的唯一文件服务拥有写权限，所有主/子 Agent 写入经同一服务和路径锁执行；恢复任务先确认上一执行者已经停止。若后续允许多个文件服务写同一工作目录，再引入跨进程锁及运行所有权约束，不能依赖普通 `asyncio.Lock` 宣称跨进程安全。

用户手工改文件也会在下次比较时被发现；正在写入临界区内的外部任意修改不受本服务锁约束。生产工作目录应只授权文件服务写入，管理员编辑也走同一条件写入接口。记录文件工具的 `tool_call_id / old_hash / new_hash / result`，便于中断后的去重与核查。

## 4. `bash` 与 CAS 的边界

**可写挂载的任意 bash 能直接覆盖文件，绕过 `write_file` 的哈希检查。** 因此建议初版命令容器将 `/rss`、当前运行 `/workspace` 均只读挂载；Agent 的持久文档写入仍通过文件工具完成。命令可在容器内 `/tmp` 做临时计算，该目录不是宿主数据挂载，不在运行完成后作为正式产物保留。工具说明应明确这一点，不能让模型以为 `echo > /workspace/artifacts/digest.md` 会成功。

如果后续确实需要 shell 生成持久文件，应单独设计暂存产物的显式导入流程，由文件服务执行同样的 CAS；不能简单把挂载改成 `rw`。目前新闻简报写作不要求这种额外流程。

命令执行参考配置（属于候选设计参数，须 Linux 实测）：

| 项目 | 候选初值 |
| --- | --- |
| 镜像 | 固定摘要的 Linux 镜像，预装 Python、bash 和必要文本处理包 |
| 身份 | 非 root UID/GID；容器运行时优先 rootless |
| 文件系统 | 容器根只读；两处业务挂载只读；`/tmp` 为限额 tmpfs |
| 网络 | `network=none`；不映射监听端口 |
| 权限 | `cap_drop=ALL`、`no-new-privileges`、保留默认 seccomp；不使用 privileged |
| 资源 | 1 CPU、256 MiB 内存、64 PID、32 MiB 临时空间 |
| 执行 | 单命令默认 10 秒，上限 30 秒；stdout+stderr 最多 16 KiB 返回 |
| 取消 | 超时或取消时停止该命令容器，确认进程退出后清理；不能只停止等待客户端 |

这些能力见 [Docker run 参数](https://docs.docker.com/reference/cli/docker/container/run/)、[none 网络](https://docs.docker.com/engine/network/drivers/none/)、[Rootless mode](https://docs.docker.com/engine/security/rootless/) 与 [seccomp 文档](https://docs.docker.com/engine/security/seccomp/)。普通容器仍共享宿主内核，这是一条经配置和验收的隔离边界，并非绝对安全保证。

不能把 Docker socket、宿主根、项目 `.env`、模型密钥或数据库凭据挂进执行容器。Docker 的管理接口本身权限很高，应由只接受固定配置的可信 `SandboxRunner` 使用，不能将任意容器参数透传给模型或前端。[Docker Engine security](https://docs.docker.com/engine/security/)

`web_search` 在 Harness 内调用 Tavily，传入受限搜索参数并返回经过限量整理的内容；联网能力不通过 bash 提供。搜索词、结果和 RSS 内容是外部数据，不拥有修改系统提示词或运行授权的能力。DeepAgents 官方同样区分“隔离执行环境”和“抵抗内容提示注入”，并建议认证工具放在沙箱外持有密钥。[DeepAgents Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes)

### Windows 开发与 Linux 运行

前端、Gateway 和普通逻辑测试可在当前 Windows 开发机运行；命令工具统一运行在 Docker Desktop 的 Linux 容器中，生产也使用 Linux 容器。WSL 2 是可行的开发入口，但 Windows/WSL 文件互访和权限语义仍须明确。[Docker Desktop WSL 2 文档](https://docs.docker.com/desktop/features/wsl/)

Docker 不可用时，管理端显示“命令沙箱不可用”，工具返回 `SANDBOX_UNAVAILABLE` 或在组装 Agent 时禁用 `bash`。禁止自动回退为宿主 `subprocess(shell=True)`。原型必须把模拟运行标清楚，不能把宿主执行冒充容器隔离验证。

## 5. 六个工具的返回预算与错误契约

下列数值是待基准测试的初始建议，不是已测容量结论。所有上限由可信配置限制，模型参数只能选更小值。

| 工具 | 建议输入/行为 | 输出边界 |
| --- | --- | --- |
| `list_dir` | 单目录、稳定排序、分页游标；不接受物理路径 | 默认 50 项，最多 200 项，总计最多 16 KiB |
| `read_file` | 1 开始的闭区间行号，默认最多 200 行；只读文本 | 最多 16 KiB；返回截断标志与下一行；极长单行报可识别错误，采集阶段将 RSS 规范化为便于逐行读取的格式 |
| `search_content` | 字面关键词、可选虚拟子目录、有限上下文行 | 默认 20 条，最多 50 条，总计最多 16 KiB；另限制扫描文件数和时间 |
| `write_file` | `expected_hash` 或 `create_new`，只允许文本产物 | 单文件内容初始上限 256 KiB；返回路径、新哈希、字节数，不回显全文 |
| `bash` | shell 命令与受限超时；固定镜像和挂载 | stdout/stderr 合计最多 16 KiB；返回 exit_code、duration、truncated、timeout |
| `web_search` | 关键词、时间范围、包含/排除域名；不接受密钥 | 默认 5 条，最多 10 条，总计最多 24 KiB；保留 URL、标题、时间、摘要与来源 |

长文件哈希采用流式读取，不能为一个行范围请求把整个大文件载入内存。采集阶段单独限制响应体及解压大小；读取预算与数据采集预算分开管理。目录条目名、Unicode、JSON 包装、异常消息也计入返回预算；不能只截断正文却让元数据无限增长。

统一成功/失败结构至少有 `ok / code / message / data / truncated`。需要区分 `INVALID_PATH`、`PERMISSION_DENIED`、`FILE_NOT_FOUND`、`FILE_CHANGED`、`FILE_ALREADY_EXISTS`、`OUTPUT_LIMIT`、`TIMEOUT`、`SANDBOX_UNAVAILABLE`。工具失败仍须生成匹配原 `tool_call_id` 的工具结果，交给 Agent 决定是否重试；这与消息修复中间件的补齐机制协同。

## 6. 可落地的运行监测

监测展示可观察到的过程：检索到哪些来源、调用了哪些工具、耗时、失败、引用与产物。无需请求、记录或展示模型私有思维链。模型公开生成的简短进度说明可作为说明字段，但不能伪装为隐藏推理。

建议初版业务运行记录和评估结果均在 MySQL；大正文和产物保存在已约定文件存储。后端为管理端提供运行列表、运行详情和 SSE 事件。LangSmith 可作为可选外接适配器，不让核心管理能力依赖外部账号；LangSmith 官方已有 traces、threads、监测和评估工作流可参考。[LangSmith Observability](https://docs.langchain.com/langsmith/observability)

### 运行和事件模型

- `AgentRun`：`run_id`、`thread_id`、`user_id`、触发方式、开始/结束时间、状态、取消原因、配置快照 ID、模型配置版本、提示词版本、输入快照 ID、产物 ID、父运行 ID。
- `RunEvent`：运行内单调 `sequence`、全局事件 ID、时间、`event_type`、`span_id`、`parent_span_id`、子 Agent 标识、可选 `tool_call_id`、脱敏 payload、耗时、错误码。
- 事件包括 queued、started、model_started、model_completed、tool_started、tool_completed、tool_failed、summary_created、message_repaired、subagent_started/completed、artifact_created、delivery_started/completed/failed、cancel_requested、cancelled、failed、completed。
- 运行状态与投递状态分开：简报生成成功后邮件失败，不应把产物删除；投递失败可以单独重试，避免再跑一次 Agent。
- SSE 用 `Last-Event-ID` 恢复，持久序号负责顺序；前端不能把连接暂断显示成运行失败。管理员按权限查看详情，用户只可访问自己的简报和运行摘要。

LangChain 支持 updates、messages、custom 等流式输出模式，但公开流事件不自动等价于本系统持久审计日志；应从框架回调和工具包装层转成自己的稳定事件模型。[LangChain Streaming](https://docs.langchain.com/oss/python/langchain/streaming)

### 成本与配置回放

记录每次模型调用的 input/output tokens、可用时的缓存/推理 token 数量、延迟、重试次数、provider request ID；token 数量不是思维链文本。主 Agent、子 Agent、摘要模型、评估模型分别计量，再聚合至运行。搜索调用数及费用另列。部分供应商不返回 usage 时标记 `unknown` 或 `estimated`，不能记作零。

成本使用本次运行的价格版本与币种计算。缓存 token 若已包含在总 input 中，不能重复相加；重试和失败但已计费的调用也要保留。LangSmith 官方成本模型同样区分输入、输出、工具成本和子运行聚合，可以作为适配目标。[LangSmith Cost tracking](https://docs.langchain.com/langsmith/cost-tracking)

管理端编辑模型参数生成新配置版本；运行创建时冻结 `model/endpoint/temperature/tool_budget/time_budget/summary_policy/prompt_version/price_version`。密钥仅引用 secret ID 和版本，不复制明文进快照。管理员可从某次运行创建调试运行，使用相同输入快照和另一组配置；“重放”是可比较的再执行，不保证模型逐字相同。

## 7. 评估与调优闭环

评估拆为确定性检查、内容评分和人工反馈。LangSmith 官方区分离线评估与在线评估，并允许代码和模型评委；开源 AgentEvals 提供严格、有序无关、子集和超集等轨迹匹配方式。本系统参考这些能力，新闻分析通常不应要求固定唯一工具顺序。[Evaluation types](https://docs.langchain.com/langsmith/evaluation-types)、[AgentEvals 源码仓库](https://github.com/langchain-ai/agentevals/blob/main/README.md)

| 维度 | 评估方法 | 调优用途 |
| --- | --- | --- |
| 偏好符合度 | 标签/排除词规则 + 语义相关性评分 + 用户反馈 | 调整关键词扩展与选稿策略 |
| 时效性 | 来源原始发布时间、抓取时间、订阅窗口 | 发现旧闻翻新、延迟采集、时区错误 |
| 事实与引用 | 引用能映射到输入证据；抽取事实与证据对照评分 | 降低没有证据支撑的总结 |
| 去重与覆盖 | 规范 URL、事件聚类、来源/主题分布 | 处理同一事件重复推送或来源单一 |
| 工具行为 | 越权访问次数、CAS 冲突恢复、工具错误重试、预算退出 | 识别权限错误、循环和上下文问题 |
| 运行效率 | 总耗时、模型/搜索/摘要成本、有效新闻数 | 选用模型、限制搜索和子 Agent 数量 |
| 投递效果 | 调度准时率、投递成功率、用户收藏/不感兴趣 | 调整推送时间和内容偏好 |

离线评估集保存用户偏好、固定的 RSS/NewsNow/Tavily 结果快照、期望覆盖事件、禁止内容与人工标注。比较配置时先用同一快照回放；联网端到端评估单独运行，因为当天新闻变化会污染实验结论。初版可准备约 20–30 个覆盖典型偏好、无结果、来源故障、重复新闻、超长文本、工具中断等场景的样例，数字是起步建议。

内容评委返回结构化评分、简短依据和证据 ID；将评委模型、提示词和 rubrics 版本一并记录，并用人工样例校准。不得让同一个 Agent 的自我评分直接决定发布质量。确定性不合格（无引用、超预算、越权、产物缺失）单列为失败，不能被主观总分平均掩盖。评委运行费用独立列出。

管理端建议提供“实验对比”：同一数据集的 A/B 配置、逐例差异、相关性/事实性/成本/耗时分布、失败样例下钻、人工标注和发布新配置。默认调优动作是选择经评估的配置版本，暂不加入无人审核的自动提示词改写与发布。

## 8. 后续必须实际验证的事项

以下是后端验收候选项，当前均未执行：

1. 路径：拒绝 `../`、嵌套父路径、反斜杠、UNC/盘符、伪同前缀根、符号链接与 junction；目录替换竞态不能越界。异常结果不泄露宿主绝对路径。
2. 隔离：A 用户/运行不能读 B 工作区；私有 RSS 不串用户；主 Agent 与子 Agent 不得提升权限。
3. CAS：读后被改会冲突；并发写只能一个成功；新文件竞争不能覆盖；部分行读取记录全文件哈希；重启恢复不能悄悄丢掉条件写保护。
4. bash：访问宿主文件、写 RSS/持久 workspace、访问数据库网络、读取密钥均失败；fork/内存/输出洪泛受到约束；取消后无遗留命令容器。
5. 上限：超长单行、Unicode、超多文件、巨大搜索结果、持续 stdout 均满足字节预算；扫描超时和截断能够被 Agent 识别。
6. 监测：事件顺序、SSE 断线续读、取消/恢复、工具失败的 ID 配对、子 Agent 成本聚合、密钥脱敏和权限过滤正确。
7. 评估：固定快照的两套配置能够产生可比较记录；未知 usage 不被记作零；内容评委失效不阻塞产物读取；投递重试不重复生成或重复发送。
8. 环境：确认 Docker Linux 容器、资源限制、rootless/权限映射和目标文件系统真实行为；未测功能必须继续标记未验证。不能用 Windows 普通单测宣称完成 Linux 沙箱验收。
