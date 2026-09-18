# 任意阶段的跨会话恢复与调整

## 目标与边界

一个产品版本可以跨任意多个会话。一次会话也可以在授权内按阶段推进，每个收尾点默认先得到用户选择。
会话只决定上下文窗口，不能决定哪个版本有效、哪些功能已完成或是否已获批准。
新会话需要访问同一持久工作区；换机器/换 Agent 时须提供对应 docs、.project-flow 与精确源码修订/未提交改动。
本工具不会读取别的聊天记录、同步磁盘、自动启动新会话，也不在会话结束后继续执行。

## 恢复协议

1. 看 AGENTS.md 和实际根目录，确认是目标项目而非同名临时目录。
2. 读 project.json。用户已指定版本时按指定版本读，未指定才用 active_version；current_delivered 只是交付文档指针。
3. 运行 `resume --root . --version v1.1.0`，读取 state、tasks、decisions、handoff 及返回的 checkpoint_notes。
4. 核对 candidate/active_baseline、来源基线、当前阶段及 resume_stage、后端 hNNN、有效授权、当前任务与依赖。
5. 核对工作树、未提交/未跟踪内容和源码观察范围；前后端的 source_roots 必须包含相关共享配置、锁文件、构建和迁移脚本，不能只选一个示例文件冒充整端。
6. 按阶段读最小资料集。先说明当前身份与下一动作，再推进仍然有效的已授权任务。

`resume.ready_to_continue=true` 只表示检查点/当前记录一致且没有等待中的阶段选择，可继续已授权工作或处理已确认转换；不代表取得了新阶段授权。
READY 仍等待后端，FRONTEND_READY 仍等待前端，BLOCKED 仍被阻塞，DELIVERED 只读历史或新建下一版。
用户当前明确暂停/变更范围时，以该指令控制下一动作，不能被旧批准记录覆盖。

## 各阶段最小读取集合

| 阶段 | 续接时额外读取 | 不要做什么 |
| --- | --- | --- |
| DISCOVER/SCOPE | 目标、版本差异、已有决定、未决问题 | 重新问已确定的用户/技术栈 |
| ITERATE | 当前原型入口、最近改动、契约、样例、反馈 | 重建原型或丢失上一轮调整 |
| SPECIFY | 草稿索引、完整性缺口、待确认决定 | 把文档未完成当已批准 |
| READY | 精确批准记录、实施分工、后端计划 | 因换会话自动开工 |
| BACKEND_BUILD/VERIFY | 后端任务、原规范、代码、验证结果、失败位置 | 越过后端开始正式前端 |
| FRONTEND_READY | 后端 hNNN、运行与鉴权说明、已批准 UX | 把后端验收当整系统完成 |
| FRONTEND_BUILD/VERIFY | 前端任务、hNNN、真实 API、原型、失败交互 | 从数据库推断私有接口或默认 mock |
| INTEGRATION_VERIFY | 两端标识、系统验证矩阵、剩余审查问题 | 复制旧通过状态代替本次证据 |
| BLOCKED | 阻塞原因、范围、恢复阶段与解决证据 | 自动清空 blocker |
| DELIVERED | 交付绑定的基线、代码、证据 | 回写历史需求/源码宣称仍是原交付 |

## 每轮保存什么

先补写 session-notes.md，模板见 assets/session-notes.template.md。记录用户本轮意图和决定来源、已完成内容、受影响/保持不变部分、具体未完成步骤、失败测试及原因、下一条操作。
更新 tasks.json 的当前阶段任务；done 必须有真实证据。中途任务保留 in_progress，不以已生成文件数量推断完成。
记录文档/原型/源码入口、基线、当前组件 code_ref、未提交修改摘要，引用可复用证据；不写真实 token、密码或生产数据。
随后调用 checkpoint，并在每次有意义修改结束/阶段切换/用户要求交接时提供 RESUME.md。

```bash
python .agents/skills/prototype-to-product/scripts/version_flow.py checkpoint --root . --version v1.1.0 --notes .project-flow/versions/v1.1.0/session-notes.md --next-action "继续后端 TASK-BE-004 的重复兑换并发测试" --expected-previous c0003
```

第一次可用 expected-previous=none。以后应传入本会话读到的上个 cNNNN，防止覆盖另一会话已更新的指针。
这只是乐观检查，不是跨机器锁，也不保证 Agent 的所有代码编辑都经过脚本。

## 新会话提示

```text
$prototype-to-product
继续当前工作区 v1.1.0 的任务。先读 .project-flow/RESUME.md，
运行 resume，核对 state、tasks、检查点与实际代码。
恢复当前阶段，沿用仍有效的决定，不新建版本或重新从零设计。
这次重点处理【本次调整或任务；没有则按已记录下一步】。
```

本提示不等于授权 READY 自动进入实现。已有 BACKEND_BUILD/FRONTEND_BUILD 的准确授权无需仅因换会话重新取得。
保存的用户原话/消息来源应来自真实对话；摘要若与当前指令冲突，先澄清具体范围，不猜测。

## 崩溃、过期与缺失

未提前保存：从当前文件、任务状态和真实代码恢复，不伪造最后一条用户批准。缺少一项信息不意味着重问整个项目。
检查点过期：resume 会列出 state/draft/runtime_files/sources 等差异类别。Agent 检查差异，保存新的决定/任务/检查点；不自动恢复旧文件。
历史 cNNNN 只供阅读，不切换当前工作状态。检查点是指纹与摘要，不是源码备份；Git/其他正常备份仍需保存未提交代码。
已冻结规范改变：先 revise，新的 bNNN 必须重新批准，旧后端交接与前端验收不转移。
源码改变但仍符合原规范：按代码缺陷处理；已验收后端变更需 reopen-backend、重验、hNNN 更新。
环境丢失：新会话重新检查依赖、端口、数据库、角色、环境变量和访问方式。旧 localhost/PID/浏览器标签不是可移植资源。允许的启动/迁移只在授权环境中运行。

## 文件权威与节流

state 是阶段/授权主源；tasks 是进度主源；冻结快照是设计主源；检查点笔记是续接信息；RESUME/INDEX 是可重建导航。
不要把主规范复制进每个会话摘要；用相对路径和稳定 ID 引用。原型反馈详细记录在当前版本，不用反复粘贴整个聊天。
默认只读当前版与当前任务相关材料，历史仅在兼容、变更解释或恢复必要时读取。

## 恢复未完成的阶段确认

state.pending_stage_review 保存当前确认点；resume 返回 pending_stage_review、awaiting_stage_decision、stage_review_fresh。检查点和版本 RESUME.md 也保存或指向它。
awaiting_user/paused：保持原阶段，先恢复该问题，不自动做下一阶段；只读请求时只报告，不强迫用户回答。
advance_confirmed：内容和范围仍有效就完成对应正式转换，不因换会话重复批准；阶段授权仍单独核对。
changes_requested：继续用户要求的修改，不拿旧答案推进；修改后再次评估并记录新的确认点。
stage_review_fresh=false：先核对实际文档、代码、任务与指定证据的变化，展示当前成果后再问，旧确认不能套在新内容上。
待确认时 ready_to_continue=false 表示不能自动执行下一动作；并不意味着成果丢失。补写会话摘要/checkpoint 不使阶段确认本身过期；指定为 artifact 的正式报告变化会使其过期。
