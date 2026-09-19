# 后端运行说明（交接候选，尚未验收）

完整本机/容器运行命令见根README.md；Python精确依赖见backend/uv.lock，模型/摘要适配版本已锁定。Gateway、worker、beat分别运行，MySQL8.4与Redis容器独立。后端源码backend，compose.yaml为开发编排。先alembic upgrade head，再CLI init（创建管理员、三个未验证默认源与MySQL checkpoint/store）；初始化不删除数据。管理员账号从backend/.env的ADMIN_EMAIL/ADMIN_PASSWORD创建，秘密不写入本交接包。

在仓库根用PowerShell执行（Python3.12、uv、Docker Linux engine）：

```powershell
uv sync --project backend --frozen
docker compose up -d mysql redis
# 首次环境：复制环境模板并填写本地密钥；已有backend/.env时保留其值。
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend python -m zhigenews.cli init
docker compose --profile app build api
docker compose --profile app run --rm api alembic upgrade head
docker compose --profile app run --rm api python -m zhigenews.cli init
docker compose --profile app up -d api worker beat
Invoke-RestMethod http://127.0.0.1:18000/healthz
```

健康结果应为status=ok/version=1.0.0；`docker compose --profile app ps`应显示5服务运行且MySQL健康。`docker compose stop`停止本项目且保留数据，不执行down -v。原生调试可用`uv run --project backend uvicorn zhigenews.gateway:app --host 127.0.0.1 --port 18000`，须先停api避免端口冲突。完整Agent工作流固定使用Linux worker。

安装冻结依赖：FastAPI0.141.1、SQLAlchemy2.0.54、LangChain1.4.1、LangGraph1.2.11、langchain-openai1.6.2、MySQL checkpoint3.0.0（pymysql/aiomysql/asyncmy）。uv.lock是准确依赖来源；API镜像与bash沙箱使用Dockerfile/配置中的固定digest。

API http://127.0.0.1:18000/api/v1；文档/openapi.json；健康/healthz。用户/管理Cookie分离，生产COOKIE_SECURE=true；开发Origin按.env.example配置，不可通配凭据CORS。客户端所有写请求发送X-Zhige-Request:1，创建生成/采集/评估/发布重试发送8–128字符Idempotency-Key，同键不同请求409。列表使用items/nextCursor、limit1–100，GET当前生成恢复无localStorage依赖。

原生开发数据库13316、Redis56386；容器服务名mysql/redis。数据卷zhigenews_runtime；trusted worker具有DockerCLI/socket用于启动沙箱，沙箱本身无socket/秘密/网络，业务挂载只读。宿主与worker使用同一卷绝对路径，使沙箱bind准确指向当前run。重启不删除卷，运行恢复取MySQL checkpoint与幂等outbox。不得把原型数据导入正式库。

后台采集按源interval与next_fetch_at、租约和文件锁；失败保留有效快照。每日按Asia/Shanghai HH:mm创建唯一business_key；首次有效偏好启用，未配置/封禁不调度；发布独立于生成，同一brief重试增加attempts，只有发布事务成功才公开100%。

模型密钥由环境主密钥加密，API只写；主密钥丢失后无法解密，生产需妥善保存。CLI环境初始模型为未验证、配置为草稿，真实能力测试后才能发布。当前缺少模型和Tavily凭据，真实探针、完整实际生成与LLM评分未通过，不能接收此交接或启动正式前端。

前置迁移0001为静态DDL，包含12个业务表，InnoDB/utf8mb4；已有表通过Alembic版本判断，不按最新ORM反向生成旧迁移。MySQL checkpoint/store由init执行官方适配器setup。升级测试在临时zg_migration_test_*库验证重复upgrade、模式一致和Unicode JSON数据重启保持；不承诺生产无损降级。

代码身份由backend-verification.json的source_fingerprint绑定backend、compose.yaml、infra。新会话运行`source-id --component backend --frozen`核对当前源码，重新build并启动后实际探测，不能仅凭旧容器health声明代码一致。此目录仍为候选，尚无hNNN。
