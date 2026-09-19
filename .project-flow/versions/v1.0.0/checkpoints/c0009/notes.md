# v1.0.0 后端独立验收记录 · 2026-09-19

用户已批准r5原型/文档，明确顺序完成全部后端→全部前端→交付，免中途确认。当前活动基线v1.0.0/b002，manifest 420ebd837df8c239cc1b3ecd4b6509ca1ebca98a3fbeaf6fba4efde2fb58e3d3。b001为未批准中间候选。baseline/backend授权已记录；前端授权须在实际hNNN存在后绑定，不能提前造交接。

后端功能代码已实现。53操作FastAPI/MySQL Gateway、匿名和管理员Cookie、偏好CAS、配额/审计、来源/模型/配置/评估管理、NewsNow/RSS不可变快照、Celery定时/租约/outbox/发布、实际create_agent/LangGraph/MySQL checkpoint/store、文件/CAS/只读Docker/bash/Tavily/子任务、消息修复/独立摘要/预算、持久事件/管理SSE/公开进度。冻结Error枚举复核发现内部码泄漏，已集中public_code映射并加实际错误schema校验；生产源码未更改批准契约。

最终全套：121 passed，0 failed/error/skipped，80.27秒；真实MySQL与Docker开关全部开启，迁移使用随机临时数据库。Ruff通过，Linux镜像构建通过；最新镜像API/worker/beat重建后真实HTTP、登录/偏好、Redis→Celery tick、worker内非root/无秘密/socket/只读沙箱再次通过。MySQL迁移重复upgrade/Unicode数据/进程重启、checkpoint pending writes与新进程恢复均有实际测试。一个Starlette anyio别名弃用警告，不影响结果。

证据：evidence/backend-junit.xml、backend-validation.json、backend-source.json、runtime-smoke.json、ingestion-live.json、live-services.json。外部NewsNow两个源及RSS真实抓取成功；Agent确定性测试只将provider换为ScriptedModel，评估worker真实create_agent/MySQL/固定快照和不发布已验证，实际LLM judge尚未验证。backend-verification.json记录15个passed检查与5个blocked检查（AC006/013/015、RUNTIME/HANDOFF），不能接受后端或开始前端。

当前阻塞：backend/.env缺OPENAI_MODEL、OPENAI_API_KEY、TAVILY_API_KEY；兼容供应商另设OPENAI_BASE_URL。已请求本地配置，未得到凭据。没有查找其他项目秘密或替用户申请服务。已有加密/IP hash/admin随机秘密保存在被忽略的backend/.env，不要覆盖或输出。模型实际能力、Tavily和真实LLM评估/生成发布仍需验证。

精确源码指纹64fd2c11f1b643bc0a53615de685626d303f55c735d7254d7f8e20548b9e42f0，范围backend、compose.yaml、infra；Git起点994e069c0cb3b688248efd3deb7ec0bc1fd522b0，本轮未提交/推送/生产部署。后端交接候选在handoff-input/（53接口逐项REQ/AC/样例/错误/证据、runbook、smoke、env、handoff.json）。无hNNN。正式双端和系统交付未开始，原型保持隔离。

服务：Docker项目zhigenews，MySQL8.4本机13316，Redis56386，Linux API18000，worker/beat已运行，数据卷保留。初始化默认源真实快照已位于容器卷；测试后确认models/configs/runs/pending-outbox均0，没有将synthetic测试任务留给worker。原生data与容器卷不能混用同一次运行。全套测试前停beat/worker，测试结束清理scoped fixture后恢复，避免队列消费测试outbox。

下一动作：凭据齐备后恢复BACKEND_VERIFY，先verify_live受限探针，再通过管理API验证真实模型并发布配置，实际生成→站内发布及LLM评估；更新真实报告/任务，清除已解决blocker；accept-backend归档hNNN，再check-backend并沿用原用户连续授权绑定frontend。进入前端前完整读取根design-user.md/design.md并复用原型视觉。不得跳过必需门槛，不能把目前状态称作完整v1.0.0交付。
