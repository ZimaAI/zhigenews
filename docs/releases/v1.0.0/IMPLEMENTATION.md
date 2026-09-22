# v1.0.0 实现与用户验收入口

前后端实现已完成，当前阶段为 `FRONTEND_VERIFY`，等待你进行最终业务验收。开发检查已通过：契约生成一致性、两端类型检查与独立生产构建、9项API客户端测试，以及记录在版本 evidence/ 中的代表性真实浏览器检查。完整生成和发布链路仍按下方步骤由你验收。

历史实施基线为v1.0.0/b003，后端交接为h001。2026-09-19按用户要求移除管理员模型与连接、Agent 配置管理；当前活动API和配置方式以工作区实现及下文为准，b003/h001保持归档。真实模型、Tavily和最终业务测试由用户随后验收，未执行的外部调用不标为通过。

2026-09-22按用户要求移除正式应用的评估实验，包括固定样例、评分、比较和评估模型配置。旧接口返回404；历史实验记录、文件、隔离原型及发布快照保留，后续重新实现。升级需同步重建并重启API、worker、beat和管理员前端。

2026-09-19 同时按用户决定移除当前长期记忆实现，包括保存、同步、读取、删除接口和摘要中间件的记忆注入。偏好与简报仍按原业务流程保存，会话摘要和 checkpoint 恢复继续使用。旧记忆记录不再读写，本次不执行数据清理；未来重新设计长期记忆时再决定数据处理方式。

## 启动应用

仓库根使用Node.js 24、Python3.12、uv和Docker Linux engine。已有`backend/.env`包含本地管理员密码与加密密钥，请保留；新环境依据`backend/.env.example`填写。

```powershell
uv sync --project backend --frozen
docker compose up -d mysql redis
docker compose --profile app build api
docker compose --profile app run --rm api alembic upgrade head
docker compose --profile app run --rm api python -m zhigenews.cli init
docker compose --profile app up -d api worker beat
npm ci
npm run build
```

生成简报需要 API、worker 和 beat 同时运行：API 创建持久任务，beat 投递任务，worker 执行生成及发布。若使用 VS Code 的 API 或全栈调试入口，准备任务会自动构建后端镜像并启动容器 worker/beat，再启动本机 API；详见[本机与调试启动步骤](../../development.md#vs-code-启动与断点调试)。本机 API 和 Linux worker 共用数据库及队列，生成工作区保存在容器数据卷。

分别在两个终端运行：

```powershell
npm run dev:user
npm run dev:admin
```

- 用户端：[http://127.0.0.1:5173](http://127.0.0.1:5173)，自动建立匿名Cookie身份。
- 管理端：[http://127.0.0.1:5174](http://127.0.0.1:5174)，用`backend/.env`中的`ADMIN_EMAIL`及`ADMIN_PASSWORD`登录。
- 后端健康：[http://127.0.0.1:18000/healthz](http://127.0.0.1:18000/healthz)。

生产构建分别输出至`apps/user-web/dist`和`apps/admin-web/dist`。停止相应dev进程后，`npm run preview:user`或`npm run preview:admin`在同一端口检查该端构建结果。两个应用都通过`/api`代理访问18000端口，使用服务端HttpOnly Cookie；自定义API地址用对应应用的`VITE_API_BASE_URL`，其Origin需在后端`ALLOWED_ORIGINS`中配置。

`npm run build:user`、`npm run build:admin`可独立构建。`npm run check:contract`核对API类型/路由与当前后端活动契约，`npm run test:api`验证客户端传输及SSE逻辑。原型仍在`draft/prototype/`，不可与正式应用占用同一开发端口。

## 配置模型和搜索

1. 在`backend/.env`填写`OPENAI_MODEL`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`及`TAVILY_API_KEY`。上下文窗口和思考开关使用`OPENAI_CONTEXT_WINDOW`、`OPENAI_THINKING_ENABLED`。
2. 摘要模型默认继承主模型；需要单独指定时设置`SUMMARY_OPENAI_*`。
3. Agent 参数、工具列表、系统提示词位于`backend/src/zhigenews/runtime_config.py`常量中。修改代码后重新构建镜像：`docker compose --profile app build api`。
4. 重新创建容器，使配置生效：`docker compose --profile app up -d --force-recreate api worker beat`；本机 API 也需重启。保持数据库和数据卷。初始化不再创建模型或 Agent 配置记录，不需要后台连接验证和配置发布。
5. 新生成自动固定当前部署配置。旧数据库配置不再用于新任务，已有运行保留创建时的快照；密钥始终只在后端配置文件和加密的私有快照中。

## 用户最终验收顺序

新闻检索已改为采集端维护索引：每个启用来源在实际采集完成后维护 `index.json`，累计最近 24 小时内发布的已采集新闻，发布时间缺失则排除。304、内容不变及失败也清理过期索引项；不会删除历史正文。升级后已有来源将在下一次采集时建立新目录和索引，也可在管理端触发采集；Agent 启动时不补建。

新运行以实际开始时间固定 24 小时窗口，首条模型消息只含偏好、时间和目录说明。Agent 自主检索只读 `/news/<source_id>`，最终按选中证据解析不可变记录并校验时间。文件工具和 bash 均可读写整个本次 `/workspace`，CAS 仅约束文件工具；其他运行目录及凭据不挂载。已有绑定证据的旧运行保留其原有资料与时钟，资料经只读 `/news/fixed` 提供，不再嵌入首条新消息。

1. 用户端自动进入→首次选择话题/关键词→保存→刷新恢复同一身份；检查错误时草稿保留、未保存离开、推送时间保存。
2. 管理端确认来源的最后成功/下次采集/周期；手动采集返回排队状态，并等待真实结果。采集失败时保留最后有效快照。
3. 用户端生成简报，管理员查看实际运行事件；确认进度来源于服务端，发布完成前不显示100%，旧简报仍可阅读。
4. 生成完成后检查新闻详情弹窗、原始链接和引用、部分来源缺失、历史搜索/日期筛选/分页；无匹配时允许空结果。
5. 验证每日调度与同一简报的站内发布重试；“已发布”仅表示站内可阅读。没有邮件渠道。
6. 检查管理员与匿名身份隔离、封禁/解封审计、429等待提示、移动端重排及键盘弹窗。

缺少模型或搜索凭证时，页面显示真实不可用/未配置结果，不提供模拟成功或假简报。当前没有生产部署；停止本项目使用`docker compose stop`，数据卷保留。实际检查结果以`.project-flow/versions/v1.0.0/`的阶段报告与证据为准。
