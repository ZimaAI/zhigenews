# 知更 · AI 新闻简报系统

产品版本 v1.0.0；当前阶段 ITERATE；原型修订 r3；来源基线、候选基线、批准基线均无。DISCOVER 成果提交为 `98fd673`，双端原型 r1 提交为 `2bfb26d`，本轮修改前 r2 提交为 `72b512a`；本轮 r3 尚未提交。本轮精简用户端、头像进入设置、仅三项偏好与站内每日时间，首次使用引导持久化；不冻结规范，也未开始正式应用实施。

## 本轮评审入口

先读 [原型运行与演示说明](../prototype/README.md)，再按需要查看：

1. [需求范围](01-requirements.md)：用户明确要求与本轮建议默认值。
2. [页面与流程](02-ux.md)：已落地的双端路由、模拟交互和候选行为。
3. [领域模型](03-domain.md)：实体、状态、权限、时间及新生成/重投的区别。
4. [契约入口](../contracts/README.md)与[唯一 OpenAPI 主源](../contracts/openapi.json)：47 schemas、51 操作及 14 份 synthetic 固定样例。
5. [验收目录](05-acceptance.md)与[双向追踪](../traceability.json)：23 项需求对应 34 项 AC，区分 frontend/backend/integration，定义不等于已通过。
6. [架构草案](04-architecture.md)：Gateway、Harness、采集、调度、存储与推送。
7. [DISCOVER 历史成果](../DISCOVERY.md)、[Agent 调研](../../../../research/agent-runtime.md)、[新闻采集调研](../../../../research/news-ingestion.md)、[沙箱与监测评估调研](../../../../research/sandbox-observability.md)。

用户端设计依据为根目录 [design-user.md](../../../../../design-user.md)，管理员端为 [design.md](../../../../../design.md)，RSS 候选清单为 [RSS.md](../../../../reference/RSS.md)。研究文件解释技术事实，产品行为以本版本草稿、未来批准基线为准。

## 尚未完成

当前可运行原型位于 `../prototype/`，包含 `user-web/`、`admin-web/` 两个 Vue 3 项目，共享语义组件与内存 adapter，分别加载各自主题和布局。新闻、运行、评估和发送结果均为模拟；没有 HTTP 后端、真实模型执行或真实定时发布。两个开发端口各有独立 localStorage，可从页顶重置。

下一轮继续调整原型、领域、契约和方案。完整正式实施/迁移规范及契约尚待细化字段，在原型定稿后的 SPECIFY 阶段整理；`scope.json` 的文档映射不表示每份文档已存在或获批准。正式后端和正式前端仍未实施，不能沿用原型通过状态作为生产验收。

正式源码计划为 `backend/`、`apps/user-web/`、`apps/admin-web/`；共享前端组件计划为 `packages/ui/`。这些目录当前尚未建立。

续接入口：[项目状态](../../../../../.project-flow/RESUME.md)。不要把本轮研究报告或工作流结构检查当成后端/前端验收通过。
