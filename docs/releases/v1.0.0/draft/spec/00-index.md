# 知更 · AI 新闻简报系统

产品版本 v1.0.0；当前阶段 DISCOVER；来源基线、候选基线、批准基线均无。当前是需求和技术探索成果，尚无可运行原型或应用实现。

## 本轮评审入口

先读 [阶段成果与下一步](../DISCOVERY.md)，再按需要查看：

1. [需求范围](01-requirements.md)：用户明确要求与本轮建议默认值。
2. [页面与首条流程](02-ux.md)：两个独立 Vue 项目的页面安排。
3. [架构草案](04-architecture.md)：Gateway、Harness、采集、调度、存储与推送。
4. [Agent 运行时调研](../../../../research/agent-runtime.md)。
5. [NewsNow / RSS / Tavily 调研](../../../../research/news-ingestion.md)。
6. [沙箱与监测评估调研](../../../../research/sandbox-observability.md)。

设计依据为仓库根目录 [design.md](../../../../../design.md)，RSS 候选清单为 [RSS.md](../../../../reference/RSS.md)。研究文件解释技术事实，产品行为以本版本草稿、未来批准基线为准。

## 尚未完成

本轮尚未进入 ITERATE。可点击原型、权威 OpenAPI 契约、固定样例、完整领域/验收/实施/迁移规范，将在对应阶段补齐。`scope.json` 的文档映射列出未来完整文档包，不表示每份文档已存在或获批准。

正式源码计划为 `backend/`、`apps/user-web/`、`apps/admin-web/`；共享前端组件计划为 `packages/ui/`。这些目录当前尚未建立。

续接入口：[项目状态](../../../../../.project-flow/RESUME.md)。不要把本轮研究报告或工作流结构检查当成后端/前端验收通过。
