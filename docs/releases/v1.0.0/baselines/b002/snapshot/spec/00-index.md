# 知更 v1.0.0 规范索引

用户于2026-09-19确认当前 r5 原型及文档通过，要求按工作流连续完成后端、前端与本地交付。此包整理冻结该批准范围，生产实现与原型隔离。

1. [需求](01-requirements.md)、[交互](02-ux.md)、[领域](03-domain.md)、[架构](04-architecture.md)。
2. [唯一OpenAPI契约](../contracts/openapi.json)、[契约说明](../contracts/README.md)及synthetic样例。
3. [验收](05-acceptance.md)、[实施](06-implementation.md)、[变化](07-changes.md)、[迁移](08-compatibility-migration.md)、[交付](09-release-plan.md)。
4. [追踪](../traceability.json)、[执行范围](../execution-plan.json)、[质量门槛](../quality-gates.json)。
5. 批准视觉：[用户规范](design-user.md)、[管理规范](design.md)、[r5原型](../prototype/README.md)。

正式源码位于 backend、apps/user-web、apps/admin-web，前端共享 packages/ui 和 packages/api-client。原型的新闻/执行/评估为模拟，原型通过状态不继承为正式验收结果。实际任务/验证及授权见 .project-flow/versions/v1.0.0，冻结后规范以基线快照为准。
