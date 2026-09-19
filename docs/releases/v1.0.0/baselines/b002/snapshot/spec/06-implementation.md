# v1.0.0 实施计划

本版以用户已确认的 r5 原型与完整规范为输入，先后端、后前端、最后系统验收。2026-09-19 用户明确要求连续完成后续全部阶段，中途无需确认；此授权只覆盖本版本地实现、验证和归档，不包含生产部署。

## 后端

1. 建立 Python/FastAPI、SQLAlchemy/Alembic、MySQL 8.4、Redis/Celery 的独立进程工程、锁文件、迁移和运行配置。
2. 实现匿名与管理员独立会话、CSRF、资源归属、原子配额、管理审计、偏好版本和每日计划。
3. 实现 NewsNow/RSS 独立采集、条件请求、不可变快照、持久调度与失败退避。
4. 实现 Harness：create_agent 自主循环、MySQL checkpoint/store、六工具、CAS 文件服务、Linux 容器 bash、消息修复、摘要及上下文渲染、子任务共享预算。
5. 实现模型与不可变 Agent 配置、生成/站内发布、outbox、取消恢复、公开进度、管理事件/SSE、固定数据集评估。
6. 逐接口核对权威 OpenAPI，独立运行 MySQL、Redis、容器沙箱和真实服务验证；通过全部 AC-BE 后归档 h001 交接。

后端测试可以使用标明 synthetic 的受控模型/HTTP fixture 检查异常与确定性行为；真实模型、Tavily、数据库与容器的必需验收不能以替身结果代替。缺少凭据时完成不依赖凭据的工作，保留真实验收未通过状态。

## 前端

只有后端全部验收和交接完成后才建立正式 apps/user-web、apps/admin-web。复用 r5 的布局、语义组件与两套主题；packages/api-client 从冻结的 OpenAPI 生成类型，正式页面不导入 prototype/mock 或 fixtures。

用户端对接匿名进入、引导、偏好、推送时间、今日/历史/详情弹窗与公开进度；管理端对接独立登录、概览、来源、模型、配置、运行/SSE、评估、匿名监测与发布。实现保存/加载/空/失败/403/429及键盘/移动端状态，构建并以真实后端做浏览器验证。

## 系统验证与交付

检查全部有效 AC、真实生成发布闭环、每日调度/重投、双端权限与故障；修复审查发现的缺陷。按 source_roots 绑定源码指纹、实际日志和操作入口，使用工作流 deliver 归档。本地交付不自动提交 Git、不推送、不改生产。

## 阶段职责

Gateway 只处理 HTTP/授权/DTO 与短事务；网络采集与 Agent 运行在 worker，模型循环在 Harness。公开生成响应不暴露管理事件。领域和交换模型按 spec/03-domain 与 contracts/openapi.json，API 客户端、测试数据及服务端校验均从同一主源衍生。

任务按 AC 的 backend/frontend/integration 分组，具体文件拆分和测试方法可随实现调整；不降低需求或验收门槛。
