# 多版本文档管理：完整快照 + 本期差异 + 全局导航

## 默认项目布局

```text
project/
├── src/ ...                         # 原有生产代码结构照旧，不每版复制一套
├── docs/releases/
│   ├── INDEX.md                     # 生成索引，不含另一份手写规范
│   ├── v1.0.0/
│   │   ├── draft/                   # 交付后仅作留存，规范权威看已交付快照
│   │   ├── baselines/b001/
│   │   │   ├── manifest.json
│   │   │   └── snapshot/            # 实际文件内容，不只是校验和
│   │   └── delivery/                # 最终规范引用、代码标识、归档证据
│   └── v1.1.0/
│       ├── draft/
│       │   ├── scope.json           # 版本、父基线、文档语义映射
│       │   ├── execution-plan.json  # 阶段顺序与源码观察范围
│       │   ├── spec/00-index.md ... 09-release-plan.md
│       │   ├── contracts/           # 本版本唯一手写契约
│       │   ├── prototype/           # 原型源码/固定样例，隔离生产构建
│       │   ├── adr/                 # 版本适用的决定与替代关系
│       │   ├── changes/             # 必要时细分的变更记录
│       │   ├── traceability.json    # 需求与验收稳定编号及链接
│       │   └── quality-gates.json   # 冻结的验证门槛，非执行结果
│       ├── baselines/b001/ ... b002/
│       ├── implementation/backend/h001/
│       └── delivery/
└── .project-flow/
    ├── project.json                 # 版本注册表、当前处理/交付指针
    ├── RESUME.md                    # 当前版本续接导航
    └── versions/v1.1.0/
        ├── state.json
        ├── decisions.md
        ├── tasks.json
        ├── handoff.md
        ├── session-notes.md
        ├── checkpoints/
        ├── backend-verification.json
        ├── frontend-verification.json
        ├── verification.json
        └── evidence/
```

此布局针对本地脚本是固定的控制路径；文档语义单元可以通过 scope.documents 映射合并或更名。
应用源码目录由 execution-plan.source_roots 指定，不做破坏性搬家；本包不导入其他格式的项目状态。改变控制路径需修改并测试工具。

## 三层职责

**第一层，导航。** INDEX.md 由 `index` 命令根据注册表和状态生成。只提供目标版本、阶段、来源、候选与交付路径。
不要创建另一份 `docs/current/requirements.md` 并手工同步。确需门户展示时，由某个明确快照生成，只读并带来源指纹。

**第二层，可修改的完整草稿。** 这是下一基线的编写区：复制精确父快照后按差异修订。草稿不是已批准事实。
未改变的内容可以原样复用，无需让模型重新生成。多份文件的存储不意味着需要把所有历史读入上下文。

**第三层，不可覆写的基线与交付归档。** `seal` 保存整棵规范树中所有纳入规则的文件字节及哈希；独立于以后如何编辑 draft。
每次定稿记录完整目标系统规范，而不是仅冻结一张变更表。`delivery` 另外固定实际通过的报告、执行清单和证据副本。
不可覆写是工具约束加哈希检查，不是操作系统只读保护、签名账本或永久备份。仍应纳入版本控制/备份策略。

## 一份完整版本文档包

| 语义单元 | 默认位置 | 必须说明 |
| --- | --- | --- |
| 索引 | 00-index.md | 本版/父版、阅读顺序、权威边界、代码与原型入口 |
| 需求 | 01-requirements.md | 本版本完整有效能力、角色、规则目标、明确范围外事项 |
| 交互 | 02-ux.md | 全部本期有效路由与行为，变化页面、角色和失败状态 |
| 领域 | 03-domain.md | 完整对象、关系、不变量、状态与权限语义 |
| 架构 | 04-architecture.md | 当前目标架构及本期影响模块、存储与事务设计 |
| 验收 | 05-acceptance.md | 本版适用的新/旧行为场景、独立预期与追踪关系 |
| 实施计划 | 06-implementation.md | 本期增量范围、阶段边界与关键依赖，任务细化留在执行时完成 |
| 本期变更 | 07-changes.md | 相对精确来源的新增/修改/保留/废弃/移除及理由 |
| 兼容迁移 | 08-compatibility-migration.md | API、DB、事件、配置、客户端与数据升级/回退边界 |
| 交付计划 | 09-release-plan.md | 验证门槛、构建/运行方式、上线前提、操作授权边界 |

小项目可把多个语义单元映射到同一份 Markdown。自动继承不会清空其他语义单元的内容；Agent 必须手工更新合并文档的本期变更章节。
无 UI/无迁移等不适用项写清依据，不能用空文件代替判断。

## 稳定编号与有效性

REQ-xxx、AC-xxx、CHG-xxx、ADR-xxx 按项目稳定分配；跨分支可带命名空间避免重复。不要每版从 001 重新编号。
版本维度与对象 ID 是联合查询条件，例如 `v1.1.0/b002 + REQ-ACT-012`。
有效需求记录 status=active 或 deprecated；移除后仍保留 status=removed、理由与替代关系。
验收不再适用则保留 retired 和理由，必要时增加验证“已被移除”的新 AC；不能删掉失败用例来制造通过。
`since` 保留首次引入版本。语义基本延续时修改同一 ID；概念完全替换时新建 ID 并保留 replaces。
结构校验只能发现编号消失、重复、无链接等问题；“是不是同一业务语义”仍需内容审查。

追踪路径：

```text
需求 ID → 有效定义 → 受影响页面/规则/契约 → 验收 ID
                                      ↓
                            本期任务 → 代码修订 → 本版证据
```

未改需求仍在完整规范中，且按质量计划保留回归；不是因为它在上一版成功就自动通过这一版。
冻结文档里只放门槛和验收定义。实际状态留在本版 tasks/verification，交付时再归档。

## 权威与冲突

目标/范围看本版需求；交互看 UX 和批准原型；不变量看领域；交换字段看本版 contracts；技术选择看架构与适用 ADR；是否通过看本版对应代码的证据。
矛盾时创建待决项，不用“最新日期优先”“PRD 永远优先”或“代码都这样写了”自动解决。
旧版文档只用于比较或理解历史，不与当前活动基线混读当作同一份要求。
外部材料不复制为伪造的自有规范；索引记录版本/提交/读取时间和确切引用，离线交接所必需的内容应在合法范围内落到本版规范中。

## 查询和导出

查询“当前系统能力”：读 current_delivered 指向的完整快照；用户问正在设计的变化才读 active_version/draft。
查询“v1.0.0 当时如何设计”：读该产品 delivery 精确引用的快照；没交付就明确这是某次候选。
比较版本：工具提供文件与需求记录差异，Agent 结合语义整理用户能理解的变更表。
查询某需求历史：`history --id` 列出每个快照里的定义与来源，Agent 再提炼变化时间线。
交给另一个 AI：`export --ref` 导出完整文档基线，说明原型运行入口、依赖、生产代码不在该包内。接手已有系统还需要指定代码起点，而不是让它重写整个产品。


## 会话与后端交接不是规范主源

每版 draft 包含 execution-plan.json；tasks、AC、gate 明确 phase。所有受管 JSON 使用 schema_version=4，执行计划与状态标记 workflow_version=4。
后端验收归档位于 docs/releases/<version>/implementation/backend/hNNN/；它绑定 bNNN，保存真实交接正文/契约/证据和后端源码指纹，不回写 snapshot。
会话检查点位于 .project-flow/versions/<version>/checkpoints/cNNNN/，保存当时的续接信息与观察指纹；RESUME.md 是导航，不是需求主源。
会话摘要、后端运行说明和规范发生矛盾时，对照批准基线定位缺陷/变更，不私自“以最新修改时间为准”。
检查点不使产品版本递增；后端重验生成 hNNN，不一定改变 bNNN；业务/契约变化必须新 bNNN；交付后变化新产品版本。
