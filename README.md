# 知更 · v1.0.0

基于 FastAPI、MySQL、LangChain/LangGraph 的个性化新闻简报。当前实施基线为 **v1.0.0/b003**，后端交接为 **h001**。b003只记录用户确认的验收安排：先完成前后端实现，真实外部模型、Tavily及最终业务验收由用户随后进行。原型位于 `docs/releases/v1.0.0/draft/prototype/`，其模拟数据与正式应用隔离。

当前阶段与剩余工作请读 [.project-flow/RESUME.md](.project-flow/RESUME.md)，实际验收结果以版本 evidence/ 中的日志为准。不能把自动化测试中的 synthetic 模型结果视为真实模型或 Tavily 服务通过。

## 正式前端

使用Node.js24，在仓库根运行`npm ci`。分别在两个终端执行：

```powershell
npm run dev:user
npm run dev:admin
```

用户端为 [127.0.0.1:5173](http://127.0.0.1:5173)，管理员端为 [127.0.0.1:5174](http://127.0.0.1:5174)。两端均代理真实后端18000端口；用户自动取得匿名Cookie，管理员使用`backend/.env`的账号密码独立登录。

`npm run build`检查契约、类型并分别构建两个应用；也可单独执行`build:user`、`build:admin`。生产输出为`apps/user-web/dist`和`apps/admin-web/dist`，停止相应dev进程后用`npm run preview:user`/`preview:admin`在原端口预览。共享API客户端由活动后端契约生成，`npm run check:contract`检查一致性，`npm run test:api`验证传输及SSE恢复；h001交接快照保持封存。

完整启动、模型配置和用户验收步骤见 [实现与验收入口](docs/releases/v1.0.0/IMPLEMENTATION.md)。模型/Tavily密钥保留在后端，不放入VITE前端变量。

## 本地后端

需要 Python 3.12、uv、Docker Linux engine。命令在仓库根执行：

```powershell
uv sync --project backend --frozen
docker compose up -d mysql redis
uv run --project backend alembic -c backend/alembic.ini upgrade head
```

复制 [backend/.env.example](backend/.env.example) 到 `backend/.env`，设置加密密钥、IP哈希密钥、管理员密码及模型/Tavily配置。当前开发工作区已生成本地安全密钥和随机管理员密码，保存在被 Git 忽略的 `backend/.env`，不要覆盖已有值。初始化从配置创建管理员，不打印密码：

```powershell
uv run --project backend python -m zhigenews.cli init
docker compose --profile app build api
docker compose --profile app up -d --wait worker beat
uv run --project backend uvicorn zhigenews.gateway:app --host 127.0.0.1 --port 18000
```

数据库仅本机 `127.0.0.1:13316`，Redis `127.0.0.1:56386`。开发容器示例使用本地开发数据库密码；正式环境需设置自己的服务凭据。API为 `http://127.0.0.1:18000/api/v1`，健康探针 `/healthz`，契约 `/openapi.json`。

本机 API 与容器 worker/beat 共用上述 MySQL 和 Redis。生成请求由 API 入库，beat 将持久任务投递到队列，worker 执行生成与发布；仅启动 API 无法完成简报。运行文件由 Linux worker 写入 `zhigenews_runtime` 卷，供 Docker 沙箱使用。修改后端代码后重新构建镜像并启动 worker/beat，确保执行器使用新代码。

## VS Code 启动与断点调试

用 VS Code 打开仓库根目录，安装工作区推荐的 Python、Python Debugger、Vue - Official 扩展，并准备 Node.js 22.12+、Python 3.12、uv 与 Microsoft Edge。先启动 Docker Desktop 的 Linux engine，后端准备任务需要 MySQL/Redis。

1. 首次使用先按上文配置 `backend/.env`，再通过「终端 → 运行任务」执行 `frontend: install`（根目录 `npm ci`）和 `backend: init`。后者会依次同步 Python 依赖、等待 MySQL/Redis 就绪、执行迁移并初始化数据库；已有 `.env` 不会被覆盖。前端依赖仅需首次安装或锁文件更新后重新安装，F5 不重复安装。
2. 在「运行和调试」选择 **后端：API（18001）**，按 F5 启动。准备任务会先同步依赖、启动 MySQL/Redis、执行迁移，再构建当前后端镜像并启动 Linux worker/beat，随后启动本机 API。在 `backend/src/zhigenews/gateway.py` 的 `health()` 内设置断点，访问 `http://127.0.0.1:18001/healthz` 即可命中。启动后自动打开 `/docs`；Shift+F5 停止调试。调试端口使用 18001，避免与 Docker API 的 18000 冲突。为保持断点稳定，未启用自动重载，修改代码后重启调试。
3. 异步任务可分别启动 **Worker（本机 solo）** 和 **Beat（本机调度）**。先停止容器中的 worker/beat（`docker compose --profile app stop worker beat`），避免争抢相同队列或重复调度。本机进程共用根目录工作路径及 `.env`；Beat 状态保存在被忽略的 `backend/.venv/`。Windows 的 solo 入口供逐步调试，涉及 Docker 沙箱挂载的完整生成流程仍使用下方 Linux 容器栈。调试结束后可用 `docker compose --profile app up -d worker beat` 恢复容器任务服务。
4. **后端：CLI** 支持选择 `environment`、`init`、`collect`、`tick` 并设置断点；后两项会执行真实工作。`backend: lint`、`backend: test` 可从任务菜单运行，测试所需服务与环境变量见「验证」章节。测试资源管理器也支持运行与调试 pytest；如曾选过其他 Python，执行「Python: Select Interpreter」选择 `backend/.venv`。
5. 选择 **全栈：用户端 + API**、**全栈：管理员端 + API** 或 **全栈：双前端 + API**，按 F5 同时启动本机 API、正式前端 Vite 和 Edge 调试，并通过 API 的准备任务启动 Linux worker/beat，支持实际生成简报。用户端为 `http://127.0.0.1:5173`，管理员端为 `http://127.0.0.1:5174`；可以在 `apps/*/src` 的 Vue/TypeScript 与 `backend/src` 的 Python 中设置断点。API 首次准备可能晚于浏览器打开，待后端就绪后刷新页面。
6. **前端：用户端 / 管理员端（正式应用）** 可单独启动浏览器调试，需要另外启动 **后端：API（18001）**。前端调试任务通过进程变量 `ZHIGENEWS_API_TARGET=http://127.0.0.1:18001` 指定代理；普通 `npm run dev:*` 和 `preview:*` 仍默认连接 18000。断点也支持共享 `packages/` 源码。联合调试停止一个会话时会停止其余调试会话；Vite 后台任务需通过「终端 → 终止任务」停止。切换普通开发、调试或原型前先停止旧 Vite，避免端口占用或复用错误的代理目标。
7. **原型：用户端 / 管理端（模拟数据）** 保留为独立入口，会自动安装原型 npm 依赖、启动 Vite 并打开 Edge。用户端为 5173，管理端为 5174；管理端同时启动用户端以提供模拟会话接口。原型没有接入正式后端，与正式前端不能同时占用相同端口。

API 调试入口执行 `backend: api prepare`，包含基础准备、镜像构建和容器 worker/beat 启动；本机 Worker、Beat 和 CLI 调试入口仍只执行 `backend: prepare`（同步依赖、启动数据库与缓存、迁移），方便独立调试。准备任务不会重复初始化管理员。调试结束后数据库、缓存和容器 worker/beat 继续运行；停止后台任务可执行 `docker compose --profile app stop worker beat`。配置见 [.vscode/launch.json](.vscode/launch.json)、[.vscode/tasks.json](.vscode/tasks.json)；配置字段遵循 [VS Code Python 调试文档](https://code.visualstudio.com/docs/python/debugging)、[联合调试文档](https://code.visualstudio.com/docs/debugtest/debugging-configuration) 与 [浏览器调试文档](https://code.visualstudio.com/docs/nodejs/browser-debugging)。

## Linux API / worker / scheduler

```powershell
docker compose --profile app build api
docker compose --profile app run --rm api alembic upgrade head
docker compose --profile app run --rm api python -m zhigenews.cli init
docker compose --profile app up -d api worker beat
```

服务使用同一 MySQL 与 Redis。单独的 beat 扫描持久计划与 outbox，Celery worker 执行采集、Agent、评估和发布。容器数据位于 `zhigenews_runtime` 卷；API/worker统一挂载到同一绝对路径，使可信worker启动的隔离bash容器能够只读绑定本次工作区。Docker socket仅供可信worker创建沙箱，绝不挂载进Agent沙箱。沙箱无网络、非root、只读根和持久挂载、资源/输出/超时受限；不可用时不回退宿主shell。

本机 API 可搭配 Linux worker/beat 完成生成，生成工作区统一使用容器数据路径。本机 solo Worker 仅用于逐步调试，不要与容器 worker 同时消费队列，或让两类 worker 接续同一运行的文件目录。`docker compose stop`保留数据；本项目不提供自动删除数据卷或无损数据库降级承诺。

## 配置与接口

`POST /auth/anonymous`自动签发HttpOnly匿名Cookie，管理员使用独立登录Cookie。所有写请求发送 `X-Zhige-Request: 1`；有Origin时必须在ALLOWED_ORIGINS白名单。创建生成、采集、评估与发布重试发送稳定 `Idempotency-Key`（8–128字符），同键不同body返回409。429遵循Retry-After。

模型连接统一在 `backend/.env` 配置，字段示例见 [backend/.env.example](backend/.env.example)。`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY` 指定主模型；`SUMMARY_OPENAI_*` 可覆盖摘要模型，未设置时继承主模型；`EVALUATION_OPENAI_MODEL` 启用可选评估模型。管理员端不再提供模型与连接、Agent 配置页面和管理 API，无需在页面验证或发布配置。

Agent 预算、工具、摘要阈值、子任务并发和系统提示词集中在 [runtime_config.py](backend/src/zhigenews/runtime_config.py) 的常量中维护。运行与评估自动使用当前部署配置，并保存私有快照；已有数据库模型和 Agent 配置不再影响新任务，历史运行仍可查询。API key 在任务快照中加密，不通过公开接口返回。修改 `.env` 后重启本机 API，并重新创建容器 worker/beat；修改代码常量后重新构建镜像并重启 API、worker、beat。

`OPENAI_THINKING_ENABLED` 控制主模型深度思考，默认关闭；`OPENAI_CONTEXT_WINDOW` 设置上下文窗口。摘要和评估模型可用对应前缀单独配置。深度思考会消耗额外时间与输出 Token，运行时间上限在 Agent 常量中调整。用户只看公开进度，完整事件/SSE只对管理员开放。`submitted`只表示站内发布，不表示已读。

当前代码已适配 `deepseek-v4-flash`、`deepseek-v4-pro`、`deepseek-flash`、`MiniMax-M3`，以及 `gpt-5.1`、`gpt-5.2`、`gpt-5.4`、`gpt-5.5` 和对应日期快照。MiniMax 使用其 API 的 adaptive/disabled 模式，GPT 使用 medium/none；未适配的模型开启时会返回明确的配置错误。参见 [MiniMax 接口说明](https://platform.minimax.io/docs/api-reference/text-openai-api)。

DeepSeek 的思考模式使用自动工具选择，并在内部保留模型协议要求的思考上下文，公开进度和管理员消息记录不展示私有思维链。最终简报仍须通过结构、引用与来源校验。参见 [DeepSeek 思考与工具调用说明](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 验证

### LangSmith 追踪

正式 LangGraph Agent 已接入 LangSmith 自动追踪，主图名为 `zhigenews.agent`，子图名为 `zhigenews.subagent`。模型、工具及摘要调用保留父子层级；`run_id`、`agent_thread_id`、`resumed` 元数据可关联站内运行。命令行模型探针和评估裁判也会记录追踪。

在现有 `backend/.env` 中设置以下字段，保留其他配置：

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<你的 LangSmith API key>
LANGSMITH_PROJECT=my-first-agent
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_WORKSPACE_ID=
```

组织级 API key 需要填入对应 `LANGSMITH_WORKSPACE_ID`；其他区域或自托管服务使用对应 endpoint。密钥仅保存在后端。未填 key 时追踪不启动，设置 `LANGSMITH_TRACING=false` 可关闭。配置由后端 Settings 显式传入 SDK，本机运行无需额外手工导出环境变量；进程环境变量优先于 `.env`。

执行 `uv sync --project backend --frozen`，重启本机 API，并执行以下命令更新容器 worker/beat；若 API 也在容器中运行，在最后一行追加 `api`：

```powershell
docker compose --profile app build api
docker compose --profile app up -d --force-recreate worker beat
uv run --project backend python -m zhigenews.cli environment
```

环境检查只显示配置状态与项目名，不输出 key。运行下方 `verify_live.py` 探针，或在用户端生成一份简报，然后在 [LangSmith](https://smith.langchain.com/) 的 `my-first-agent` 项目查看新 trace。模型探针名为 `zhigenews.live_model_probe`，评估裁判名为 `zhigenews.evaluation_judge`；评估运行附带 `evaluation_id`。

启用后会上传提示词、新闻证据、可见模型输出和工具输入输出，便于排查运行过程；上传前移除结构化私有思考字段及已识别的密钥。模型内部协议重放与检查点保持原状。自动化测试使用离线模拟导出，不会向真实项目发送 synthetic 数据。接入与配置方式参见 [LangChain/LangGraph 追踪文档](https://docs.langchain.com/langsmith/trace-with-langchain) 和 [敏感数据过滤文档](https://docs.langchain.com/langsmith/mask-inputs-outputs)。

### 自动化与外部依赖检查

```powershell
$env:HARNESS_TEST_MYSQL_URL='mysql+pymysql://zhigenews:local-development@127.0.0.1:13316/zhigenews'
$env:HARNESS_TEST_DOCKER='1'
uv run --project backend pytest backend/tests -q
uv run --project backend ruff check backend
uv run --project backend python backend/scripts/verify_live.py --report .project-flow/versions/v1.0.0/evidence/live-services.json
Get-Content backend/scripts/verify_runtime.py -Raw | docker compose exec -T worker python -
```

测试使用独立测试标识并清理其记录；MySQL、Docker验收须实际开启对应环境，skipped不算通过。`verify_live.py`最多一次模型工具调用和一次Tavily检索，缺少配置明确返回blocked。完整系统验收还要求真实生成、发布、调度与两个正式前端，不能以这些依赖探针代替。

全套测试前先停止beat/worker，避免调度消费测试outbox，完成后再启动。迁移测试还需设置`MIGRATION_ADMIN_DATABASE_URL`指向本地MySQL管理员连接；仅创建/清理随机命名的`zg_migration_test_*`临时库。`verify_runtime.py`验证容器HTTP、队列与嵌套沙箱，并清理自己的synthetic reader；它不验证外部模型。

详细规范见 [基线索引](docs/releases/v1.0.0/baselines/b003/snapshot/spec/00-index.md)，运行事件仅记录可展示结果、耗时和脱敏工具摘要，不采集模型私有思维链。
