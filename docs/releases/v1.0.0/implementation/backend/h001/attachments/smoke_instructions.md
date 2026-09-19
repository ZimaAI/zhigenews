# 可重复验证

1. 按runbook启动隔离开发MySQL/Redis并迁移、初始化。
2. 设置HARNESS_TEST_MYSQL_URL指向隔离开发库，HARNESS_TEST_DOCKER=1。迁移测试设置MIGRATION_ADMIN_DATABASE_URL，只在临时zg_migration_test_*库验证并清理。
3. `uv run --project backend pytest backend/tests -q`：API/完整53操作/评估/采集/worker/create_agent/CAS/MySQL重启/真实Docker。测试模型明确synthetic，输出不能证明真实模型调用成功。
4. `uv run --project backend ruff check backend`；`docker compose --profile app build api`。
5. `uv run --project backend python backend/scripts/verify_live.py --report .project-flow/versions/v1.0.0/evidence/live-services.json`，仅最多一次真实模型工具调用及一次Tavily搜索，缺凭据blocked。服务探针不代替实际生成/发布/评分全链路。
6. 用独立Cookie保存偏好，管理员设置/验证模型并发布配置；创建生成202，worker执行；发布前不100，成功后读取公开简报（不含runId/config/tools）。取消/封禁/429按API测试对应失败路径验证。管理SSE使用Last-Event-ID，只在当前run回放run.event。

容器可重复冒烟（在仓库根PowerShell执行，使用真实HTTP/Redis/worker/Docker，自动清理本次synthetic reader）：

```powershell
Get-Content backend/scripts/verify_runtime.py -Raw | docker compose exec -T worker python -
```

结果status=passed，包含health、匿名Cookie/偏好、管理登录退出、Celery ping与真实tick任务、worker内只读非root沙箱；不调用模型/Tavily，不把结果称作生成成功。完整测试前先`docker compose stop beat worker`，避免开发调度消费测试outbox；测试结束后确认scoped fixture已清理，再`docker compose --profile app up -d worker beat`。测试仅指向本项目开发库；MySQL管理员URL只用于创建独有临时迁移库。

测试不依赖正式前端。按用户本轮安排接受当前后端实现交接；真实服务与完整闭环仍待其最终验收，不把deferred记为通过。


本次交接基线为v1.0.0/b003；相较b002仅调整验收责任/时点，API契约字节与后端源码均相同，故文中b002契约链接仍为同一接口定义。用户原话与未验证项见evidence/user-acceptance-arrangement.json及backend-verification.json。
