# 移除正式应用的评估实验功能

Type: task
Status: resolved
Blocked by: none

## Answer

已删除管理页与导航、6 个 API 操作和 9 个 DTO、固定样例业务、评分器、实验执行/恢复任务及模型配置，重新生成客户端。更新设计规范、运行与部署文档；保留历史资料及数据，不再调度旧实验。

验证结果：

- 后端离线回归：164 passed、6 skipped、93 deselected；包含旧接口 404 和旧 outbox 不阻塞当前任务。
- `npm run build`：契约一致性、类型检查、用户端与管理员端生产构建通过。
- `npm run test:api`：9 项通过。
- 受影响后端文件 Ruff 检查与 `git diff --check` 通过。
- MySQL 连接返回 OperationalError，未执行数据库集成测试；未执行真实模型、Docker 集成或浏览器交互检查。
