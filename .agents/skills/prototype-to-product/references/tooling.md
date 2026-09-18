# 本地工具手册

公开入口只有 `scripts/version_flow.py`，Python 3.10+ 标准库，不需安装第三方库。
`_storage.py` 只提供当前格式的存储操作，不可作为独立工作流 CLI。受管 JSON 使用 schema_version=4，执行状态/计划使用 workflow_version=4；不导入、读取或转换其他格式。
所有示例在持久项目/共同工作区根目录执行，替换真实版本/路径/用户原话；不要把示例批准当真实批准。

## 阶段末尾询问与回答记录

这些是给 Agent 的管理命令，不要求用户手工执行。默认先读 stage-controls.md，每个阶段收尾先登记并展示问题，等待真实回复。
下面以 SPECIFY 中**实际存在、已完成核查的**候选为例；先完成 seal，替换实际版本和文件路径：

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py review-stage --root . --version v1.0.0 --to READY --summary "本阶段真实成果和验证摘要" --artifact docs/releases/v1.0.0/baselines/b001/manifest.json --remaining "已披露的非阻塞限制；没有则写无"
```

保存返回的 qNNNN；将 question 与实际摘要、产物入口展示给用户，checkpoint 后保持当前 stage 并结束本轮。只有收到真实回答后才运行：

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py answer-review --root . --version v1.0.0 --review-id q0001 --decision advance --quote "用户实际回复" --context "真实消息来源"
```

`advance` 只记录选择，不自动批准或转阶段。核对回答所指范围，再调用对应的 stage/approve/accept-backend/deliver。例如此处仍须 approve --kind baseline；其 quote/context 使用同一真实回答与被展示的明确基线上下文。
选择继续修改使用 `--decision modify`；选择暂停使用 `--decision pause`。两者都保持阶段，不执行推进命令；修改冻结规范仍要 revise。不能将工具手册里的示例原话当作用户授权。

review-stage 自动绑定当前阶段、候选/活动基线、后端交接、受管草稿和声明源码范围、tasks.json，以及每个 `--artifact` 指定文件的指纹。确认记录、history、next_action、检查点指针及普通会话笔记不会使它自身过期。
应显式加入阶段报告、实际日志、后端交接输入和相关附件；只列一份 manifest 无法自动覆盖它以外的全部运行证据。不能观察实际服务/数据库状态，换会话仍须实地核对环境。
相同内容和摘要的未回答问题复用 qNNNN；修改后新建确认点，旧问题/答案保留历史，不把旧同意转移。
已有 pending 时，向前转换命令拒绝未回答、非推进选择、错阶段或内容过期的记录；通过正常转换才清除活动确认点。规范修订、后端重开或 BLOCKED 会使原确认失效。
`resume` 返回 pending_stage_review、awaiting_stage_decision、stage_review_fresh；它只读，不代用户回答。等待回答或暂停时 ready_to_continue=false，不表示阶段产物丢失。

**工具边界**：是否到阶段末尾、是否真实询问、用户回复的语义和授权真实性由 Agent 判断。脚本防护针对已登记的确认点，不强制所有低层命令都带聊天证明，也不替模型完成验收。无确认记录不代表用户已同意；Agent 仍必须遵守默认询问协议。
后面的命令块是参数示例，不是可以不经阶段选择整段执行的脚本。

## 版本与文档操作

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py init --root . --version v1.0.0 --name MyProject
python .agents/skills/prototype-to-product/scripts/version_flow.py new --root . --version v1.1.0 --from v1.0.0/b002
python .agents/skills/prototype-to-product/scripts/version_flow.py status --root .
python .agents/skills/prototype-to-product/scripts/version_flow.py switch --root . --version v1.1.0
python .agents/skills/prototype-to-product/scripts/version_flow.py seal --root . --version v1.1.0
python .agents/skills/prototype-to-product/scripts/version_flow.py check --root . --ref v1.1.0/b001 --against-draft
python .agents/skills/prototype-to-product/scripts/version_flow.py diff --root . --left v1.0.0/b002 --right v1.1.0/draft
python .agents/skills/prototype-to-product/scripts/version_flow.py history --root . --id REQ-ACT-001
python .agents/skills/prototype-to-product/scripts/version_flow.py index --root .
python .agents/skills/prototype-to-product/scripts/version_flow.py export --root . --ref v1.1.0/b001 --output exports/v1.1.0-b001.zip
```

init/new 只创建草稿与状态，Agent 仍须填写完整规范。new 不继承授权、通过状态、检查点或 hNNN。
未交付来源只有明确 --allow-unreleased 可提前规划；精确父基线交付前不能构建。
switch 仅改文档活动版本，不切 Git。export 只导出完整规范快照，不含生产源码、会话运行状态或后端交接；跨环境继续任务还需对应工作区文件。

## 规划阶段与 SPECIFY → READY

用户一般只发自然语言，Agent 调用工具。先读 [阶段控制](stage-controls.md)。

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py stage --root . --version v1.0.0 --to ITERATE
python .agents/skills/prototype-to-product/scripts/version_flow.py stage --root . --version v1.0.0 --to SPECIFY
python .agents/skills/prototype-to-product/scripts/version_flow.py seal --root . --version v1.0.0
```

`stage --to SPECIFY` 开始整理，不代表文档已完成；`seal` 完成结构检查并新建候选快照，仍停在 SPECIFY。
获得对已展示具体候选的真实批准后才执行（引用以 seal 返回值为准）：

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py approve --root . --ref v1.0.0/b001 --kind baseline --quote "真实用户对该具体基线的批准原话" --context "真实消息来源"
```

该操作进入 READY，不写正式代码。没有候选时不能 approve；已存在且内容未变的候选不要为批准再次 seal。
READY 不能由 `stage --to READY` 设置；新后端授权才通过 `approve --kind backend` 进入 BACKEND_BUILD。
不要把本手册或使用示例里的台词复制成真实授权。基线号和 quote/context 必须来自实际工作区与用户消息。

## 每个阶段都可以 checkpoint / resume

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py checkpoint --root . --version v1.1.0 --notes .project-flow/versions/v1.1.0/session-notes.md --next-action "继续当前任务" --expected-previous none
python .agents/skills/prototype-to-product/scripts/version_flow.py resume --root . --version v1.1.0
python .agents/skills/prototype-to-product/scripts/version_flow.py resume --root . --version v1.1.0 --checkpoint c0001
```

notes 是 Agent 已写好的真实会话工作摘要；checkpoint 不自动理解对话，也不抓取聊天记录。首次 previous=none，之后传入已读取的 cNNNN。
checkpoint 新建不可覆写的检查点目录，记录阶段、基线、下一动作以及 state/draft/tasks/decisions/handoff 和声明源码范围指纹；更新最新入口，不推进阶段。
resume 只读：返回当前状态、检查点、差异和读取顺序。ready_to_continue=false 时先看是否为待回答/暂停，再核对缺失或差异；不从零重做，不自动跨阶段。
指定旧 cNNNN 是历史查询，不恢复旧文件。新会话始终需要重新核对环境/服务/实际身份；该命令没有运行这些探测。

## 批准后端 → 验收 → 批准前端

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py approve --root . --ref v1.1.0/b001 --kind baseline --quote "替换为真实用户对该基线的批准原话" --context "真实消息来源"
python .agents/skills/prototype-to-product/scripts/version_flow.py approve --root . --ref v1.1.0/b001 --kind backend --quote "替换为真实后端实施授权" --context "真实消息来源" --code-ref "准确后端起点与未提交快照"
python .agents/skills/prototype-to-product/scripts/version_flow.py check --root . --ref v1.1.0/b001 --for-build
python .agents/skills/prototype-to-product/scripts/version_flow.py stage --root . --version v1.1.0 --to BACKEND_VERIFY
python .agents/skills/prototype-to-product/scripts/version_flow.py source-id --root . --version v1.1.0 --component backend --frozen
python .agents/skills/prototype-to-product/scripts/version_flow.py accept-backend --root . --version v1.1.0 --report .project-flow/versions/v1.1.0/backend-verification.json --handoff .project-flow/versions/v1.1.0/handoff-input/handoff.json
```

Agent 在执行真实后端检查后填写 phase=backend 报告。source-id 返回实际观察指纹供报告绑定，它不运行测试或查询 Git。
accept-backend 检查当前阶段、批准/基线、已完成后端任务、必需结果、代码指纹与交接输入；复制契约、报告、任务、交接及证据字节，进入 FRONTEND_READY。
该命令从不自动进入前端，即使 plan.pause_after_backend=false。false 只是连续执行偏好，不关闭阶段末尾询问；Agent 必须核对真实条件授权和当前用户选择后再单独记录 frontend。

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py check-backend --root . --version v1.1.0
python .agents/skills/prototype-to-product/scripts/version_flow.py approve --root . --ref v1.1.0/b001 --kind frontend --quote "替换为真实前端实施授权" --context "真实消息来源" --code-ref "准确前端代码起点"
python .agents/skills/prototype-to-product/scripts/version_flow.py stage --root . --version v1.1.0 --to FRONTEND_VERIFY
python .agents/skills/prototype-to-product/scripts/version_flow.py source-id --root . --version v1.1.0 --component frontend --frozen
python .agents/skills/prototype-to-product/scripts/version_flow.py stage --root . --version v1.1.0 --to INTEGRATION_VERIFY --report .project-flow/versions/v1.1.0/frontend-verification.json
```

新前端会话应先 resume、check-backend、阅读交接并实际核对服务。批准 frontend 会把当前 hNNN 与其 hash 写入授权记录。
FRONTEND_VERIFY → INTEGRATION_VERIFY 需要真实前端报告和已完成前端任务；不会因 stage 名字更改就绕过验证记录。
旧 hNNN 查档用 `check-backend --handoff-id h001 --archive-only`，该选项不检查当前源码，不能替代前端开工 live 门槛。

## 缺陷、规范修订、阻塞

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py reopen-backend --root . --version v1.1.0 --reason "实现不符合原契约的具体缺陷"
python .agents/skills/prototype-to-product/scripts/version_flow.py revise --root . --version v1.1.0 --reason "用户批准讨论的产品/接口语义变更"
python .agents/skills/prototype-to-product/scripts/version_flow.py stage --root . --version v1.1.0 --to BLOCKED --reason "具体阻塞"
```

reopen-backend 用于未改规范的后端修复，进入 BACKEND_BUILD，停用活动交接，保留历史 hNNN，所有任务保守标记 needs_revalidation。
revise 进入 ITERATE，停用旧基线授权与活动交接，保留历史，再 seal/批准。旧代码可复用，不能继承通过状态。
阻塞解除后，Agent 先记录实际解决证据、清除对应活动 blockers，再 stage 回已保存 resume_stage；新会话不能自动清除。
不要用 stage 写入 READY/FRONTEND_READY/DELIVERED；这些只能经过批准、后端接受与最终归档门槛。

## 完整交付与检查

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py deliver --root . --version v1.1.0 --report .project-flow/versions/v1.1.0/verification.json
python .agents/skills/prototype-to-product/scripts/version_flow.py check-delivery --root . --version v1.1.0
python .agents/skills/prototype-to-product/scripts/version_flow.py promote --root . --version v1.1.0 --expected-current v1.0.0/b002 --quote "真实更新交付文档指针的要求" --context "真实来源"
python .agents/skills/prototype-to-product/scripts/version_flow.py doctor --root .
```

最终报告 schema_version=4、phase=integration，绑定两个 source_fingerprints、活动 backend_handoff/hash，以及完整有效必需检查集合。所有本版任务完成才能归档。
deliver 复制验证报告/任务/证据，不运行测试；promote 改文档指针，不部署。不同谱系默认阻止指针倒退，需要前移记录或明确 --allow-divergence --reason。
doctor 检查快照、交付、后端交接与检查点完整性及未注册目录；只检测，不自动修复。真正的源代码语义、环境、API 兼容和批准真实性仍靠 Agent 核验。

## 观察范围与安全限制

规范 scan 固定忽略：.git、node_modules、.venv、venv、__pycache__、.pytest_cache、.mypy_cache、.ruff_cache、.next、dist、build、coverage、test-results、playwright-report 及 .DS_Store/pyc/pyo。
规范/归档拒绝受管符号链接、非规范路径和常见密钥/.env 文件名；.env.example/.env.template 可含非秘密示例。
源码观察额外忽略 .project-flow、.idea、.vscode、.cache、logs、tmp、target；跳过本地 .env 系列和常见密钥，不读取这些秘密来算指纹。
共同配置、锁文件或迁移脚本位于组件之外时，把它们列入相应 source_roots。指纹只能覆盖声明范围，不完整列表会漏检；输出目录排除也可能要求项目调整源码位置/规则。
这些是防误操作措施，不是完整秘密扫描、权限沙箱、供应链签名或行为证明。不要把真实凭据放入任意交接 Markdown/日志，名称过滤检测不到其中所有秘密。
单次 CLI 有本地排他锁，JSON 多数原子替换，整个多文件动作非事务；无法自动解决多机器并发与所有崩溃情形。先看 owner/process 再处理遗留锁。
