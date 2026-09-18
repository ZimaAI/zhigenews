# Prototype to Product · 原型驱动交付

**Skill 4.1.0 · 当前格式专用**

通过可运行前端原型、领域与数据设计讨论产品，达成共识后生成完整规范并批准基线；先实现并验收后端、留下交接包，再实现真实前端，最后验证完整系统。
支持产品多版本迭代、任意阶段跨会话续接。实现、测试与验证方法在已批准目标和授权边界内由模型自主决定，不强制固定开发步骤或 TDD。

## 安装

将整个目录放在项目工作区：

```text
.agents/skills/prototype-to-product/
```

必须保留 references、assets、scripts。Codex CLI/IDE 中在对话输入 `$prototype-to-product` 显式选择；这不是 shell 命令。隐式调用关闭。
本地技能装载方式的官方资料见 [SOURCES.md](SOURCES.md)；用户机器安装未实测。

本包只处理 schema_version=4；执行状态和计划使用 workflow_version=4，不提供其他格式的接入、兼容分支或迁移工具。
不要把不受支持的状态格式号直接改成 4，不要覆盖/删除已有业务文档或 .project-flow 来假装接入成功。
此限制针对 **Skill 管理数据的格式**；使用本包创建的产品仍能从 v1.0.0 持续演进，历史快照、补丁线、接口兼容和业务数据库升级设计仍保留。

## 阶段末尾由 AI 主动询问

你不需要猜当前是否可以进入下一阶段。AI 判断当前阶段已具备收尾条件时，会展示实际成果、入口、验证和限制，然后问：

> 你希望进入下一阶段，还是继续修改当前阶段的内容？也可以先停在这里。

默认保持当前 stage，保存 pending_stage_review 和检查点，收到选择后才推进。你选修改就继续修改；选暂停就留下同一版本的续接入口。新会话会恢复同一个选择点，不把换会话当作同意。
对 SPECIFY，问法明确为“批准已展示的具体基线进入 READY，还是继续修改规范”；批准文档不等于开工。实现内的任务安排、测试和排错仍交由模型自主决定。

## 最常用的四句话

首次在任一会话使用先显式调用 `$prototype-to-product`，随后可以自然语言操作：

| 目的 | 可以直接说 |
| --- | --- |
| 接着未完成阶段做 | 继续当前版本的未完成任务。先恢复状态和检查点，不新建版本，不重新规划。 |
| 原型定稿 | 当前原型与数据设计可以定稿，进入 SPECIFY 整理完整文档，先不要实现。 |
| 文档批准 | 批准已展示的 v1.0.0/b001 文档基线，进入 READY，暂时不要实现。 |
| 后端开始 | 按已批准基线开始后端实现；验收和交接后停在 FRONTEND_READY。 |

**先确认实际基线号再批准，不机械照抄示例。** 没有候选时先让 AI 完成 SPECIFY 并展示候选；换会话不会使候选自动获批。

完整的逐阶段提示、前端接手、版本切换和故障恢复见 **[使用手册](USAGE.zh-CN.md)**。

## 阶段图

```text
DISCOVER / SCOPE → ITERATE → SPECIFY → READY
                                        ↓ 后端授权
                     BACKEND_BUILD → BACKEND_VERIFY
                                        ↓ 独立验收/交接
                                  FRONTEND_READY
                                        ↓ 前端授权
                    FRONTEND_BUILD → FRONTEND_VERIFY
                                        ↓
                         INTEGRATION_VERIFY → DELIVERED
```

每个阶段中途都能换会话。每条箭头默认先由 AI 展示成果并询问推进还是修改；得到选择后才推进，内部实现/测试不逐项询问。后端交接默认暂停；用户明确免除具体阶段范围的重复询问时，仍按顺序取得验收和准确授权。
READY = 文档已批准、等后端开工授权；FRONTEND_READY = 后端已验收、等前端开工授权。两者都不是“等待下一条会话才能工作”。

## 工作区

```text
workspace/
├── .agents/skills/prototype-to-product/    # Skill 自身
├── backend/                              # 正式代码路径可配置
├── frontend/
├── docs/releases/
│   ├── INDEX.md                          # 生成导航
│   └── v1.0.0/
│       ├── draft/                        # 本版完整规范 + 差异
│       ├── baselines/b001/                # 文档快照
│       ├── implementation/backend/h001/   # 后端验收交接
│       └── delivery/                     # 完整系统归档
└── .project-flow/
    ├── project.json
    ├── RESUME.md
    └── versions/v1.0.0/
        ├── state.json
        ├── tasks.json
        ├── decisions.md
        ├── handoff.md
        ├── session-notes.md
        ├── RESUME.md
        ├── checkpoints/c0001/
        ├── backend-verification.json
        ├── frontend-verification.json
        ├── verification.json
        └── evidence/
```

前后端可在共同父工作区下的独立仓库。新会话必须访问对应工作区资料与准确源码/未提交修改，不会自动继承另一会话的磁盘、进程或登录状态。
代码位置由 execution-plan.source_roots 指定；文档版本切换不是 Git checkout。

## 工具与边界

公开入口 `scripts/version_flow.py` 管理版本、快照、精确批准、状态、检查点、后端交接和交付归档；review-stage/answer-review 记录阶段收尾问题和用户选择，resume 恢复待确认状态。通常由 AI 调用，你使用自然语言即可。
参数见 [工具手册](references/tooling.md)，状态转换规则见 [阶段控制](references/stage-controls.md)。
工具对已登记的确认点阻止未确认或过期的向前转换；不判断模型是否真的询问，也不把任何示例文本当作真实授权。工具只验证文件、路径、记录、指纹与阶段门槛；不会替你运行应用测试，也不能证明用户身份、需求正确性、测试真实性或生产部署状态。
源码观察只覆盖声明范围；文档快照和检查点不是完整源码备份。单工作区顺序交接，不保证多会话并发写入安全。
缺环境、未执行或仅 mock 成功不能写成真实通过；部署、真实资金和破坏性生产操作需独立授权。

## 验证

```bash
python -m unittest discover -s tests -v
```

实际结果见 [TEST-RESULTS.txt](TEST-RESULTS.txt)，包装检查见 [PACKAGE-VALIDATION.txt](PACKAGE-VALIDATION.txt)。
测试使用隔离文件夹及明确标注 SYNTHETIC 的授权/日志，只检查工具行为，不代表真实项目验收。
[EVALUATION.md](EVALUATION.md) 是待在实际宿主执行的模型行为用例；本包没有声称已完成用户环境的全栈开发、升级或生产部署演练。

[主指令](SKILL.md) · [使用手册](USAGE.zh-CN.md) · [自主实施](references/implement.md) · [跨会话续接](references/sessions.md)
