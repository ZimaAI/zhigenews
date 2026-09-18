# 知更 · AI 新闻简报系统

产品版本v1.0.0；当前阶段ITERATE；原型修订r5；来源、候选、批准基线均无。历史r1为 `2bfb26d`，r2为 `72b512a`，r3为 `e7251f3`。本轮在r4候选视觉上新增自动匿名Cookie身份、新闻详情弹窗、公开生成进度和匿名防滥用监测；移除用户注册/密码登录、阅读标记及整理记录。用户设计3.2、管理员设计2.2。欢迎页沿用旧视觉但只作自动进入/加载/失败重试，已获用户确认。正式实现仍未授权或开始。

## 本轮评审入口

先读 [原型运行与演示说明](../prototype/README.md)，再按需要查看：

1. [需求范围](01-requirements.md)：用户明确要求与本轮建议默认值。
2. [页面与流程](02-ux.md)：已落地的双端路由、模拟交互和候选行为。
3. [领域模型](03-domain.md)：实体、状态、权限、时间及新生成/重投的区别。
4. [契约入口](../contracts/README.md)与[唯一 OpenAPI 主源](../contracts/openapi.json)：50 schemas、52 操作及 22 份 synthetic 固定样例。
5. [验收目录](05-acceptance.md)与[双向追踪](../traceability.json)：24 项需求对应 36 项 AC，区分 frontend/backend/integration，定义不等于已通过。
6. [架构草案](04-architecture.md)：Gateway、Harness、采集、调度、存储与推送。
7. [DISCOVER 历史成果](../DISCOVERY.md)、[Agent 调研](../../../../research/agent-runtime.md)、[新闻采集调研](../../../../research/news-ingestion.md)、[沙箱与监测评估调研](../../../../research/sandbox-observability.md)。

用户端设计依据为根目录 [design-user.md](../../../../../design-user.md)，管理员端为 [design.md](../../../../../design.md)，RSS 候选清单为 [RSS.md](../../../../reference/RSS.md)。研究文件解释技术事实，产品行为以本版本草稿、未来批准基线为准。

## 尚未完成

当前可运行原型位于 `../prototype/`，包含 `user-web/`、`admin-web/` 两个 Vue 3 项目，共享语义组件与内存 adapter，分别加载各自主题和布局。新闻、运行、评估和发布结果均为模拟；r5通过Vite开发专用 /__demo 服务演示HttpOnly Cookie、账户统计、限流/封禁，两端共享匿名监测，其他业务仍由集中mock管理。没有正式FastAPI/MySQL、真实模型执行或真实定时发布。

下一轮继续调整原型、领域、契约和方案。完整正式实施/迁移规范及契约尚待细化字段，在原型定稿后的 SPECIFY 阶段整理；`scope.json` 的文档映射不表示每份文档已存在或获批准。正式后端和正式前端仍未实施，不能沿用原型通过状态作为生产验收。

正式源码计划为 `backend/`、`apps/user-web/`、`apps/admin-web/`；共享前端组件计划为 `packages/ui/`。这些目录当前尚未建立。

续接入口：[项目状态](../../../../../.project-flow/RESUME.md)。不要把本轮研究报告或工作流结构检查当成后端/前端验收通过。
