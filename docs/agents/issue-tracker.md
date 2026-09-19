# Issue tracker: Local Markdown

任务与规格存放于 `.scratch/`。

## 文件约定

- 每个功能独立目录：`.scratch/<feature-slug>/`。
- 规格文件：`spec.md`。
- 实现任务：`issues/<NN>-<slug>.md`，从 01 编号，每项任务独立文件。
- 评论与讨论追加在任务文件末尾的 `## Comments` 下。

## 技能操作

- “发布到任务系统”：在对应功能目录下创建 Markdown 文件。
- “获取相关任务”：读取用户指定路径的文件；仅提供编号且无法唯一定位时，先澄清。
- 未配置 triage 标签体系。

## 探索任务约定

供 wayfinder 类工作流使用：

- 探索地图：`.scratch/<effort>/map.md`，记录笔记、已定决策与待澄清事项。
- 子任务：`issues/<NN>-<slug>.md`。
- `Type:` 为 research、prototype、grilling 或 task。
- `Status:` 为 open、claimed 或 resolved。
- `Blocked by:` 列出依赖任务编号，依赖全部 resolved 后解除阻塞。
- 按编号领取未阻塞的 open 任务，开始前保存为 claimed。
- 完成后在 `## Answer` 下追加结果，标记 resolved，并在地图中补充摘要与链接。

## 与现有项目流程的关系

这些文件供工程技能管理规格与任务。
当前产品版本和阶段仍以 AGENTS.md 指定的项目流程记录为准。
