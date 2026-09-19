# v1.0.0 实现与用户验收入口

前后端实现已完成，当前阶段为 `FRONTEND_VERIFY`，等待你进行最终业务验收。开发检查已通过：契约生成一致性、两端类型检查与独立生产构建、9项API客户端测试，以及记录在版本 evidence/ 中的代表性真实浏览器检查。完整生成、评估和发布链路仍按下方步骤由你验收。

当前功能与API来自v1.0.0/b003，后端交接为h001。b003相较b002只记录用户确认的验收安排：先完成整个项目实现，真实模型、Tavily、LLM评分和最终业务测试由用户随后验收。后端原有121项测试和实际数据库/容器证据保留，未执行的外部调用仍未标为通过。

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

分别在两个终端运行：

```powershell
npm run dev:user
npm run dev:admin
```

- 用户端：[http://127.0.0.1:5173](http://127.0.0.1:5173)，自动建立匿名Cookie身份。
- 管理端：[http://127.0.0.1:5174](http://127.0.0.1:5174)，用`backend/.env`中的`ADMIN_EMAIL`及`ADMIN_PASSWORD`登录。
- 后端健康：[http://127.0.0.1:18000/healthz](http://127.0.0.1:18000/healthz)。

生产构建分别输出至`apps/user-web/dist`和`apps/admin-web/dist`。停止相应dev进程后，`npm run preview:user`或`npm run preview:admin`在同一端口检查该端构建结果。两个应用都通过`/api`代理访问18000端口，使用服务端HttpOnly Cookie；自定义API地址用对应应用的`VITE_API_BASE_URL`，其Origin需在后端`ALLOWED_ORIGINS`中配置。

`npm run build:user`、`npm run build:admin`可独立构建。`npm run check:contract`核对API类型/路由与h001冻结契约，`npm run test:api`验证客户端传输及SSE逻辑。原型仍在`draft/prototype/`，不可与正式应用占用同一开发端口。

## 配置模型和搜索

1. 在`backend/.env`填写`TAVILY_API_KEY`。如希望CLI初始化模型草稿，同时填写`OPENAI_MODEL`、`OPENAI_API_KEY`，自定义兼容供应商另填`OPENAI_BASE_URL`。
2. 重新创建容器，使环境变量生效：`docker compose --profile app up -d --force-recreate api worker beat`。保持数据库和数据卷。
3. 在管理端“模型配置”录入或编辑模型、端点、角色及密钥，执行真实连接测试。密钥只写，不在页面回显；未验证模型不能发布为可用Agent配置。
4. 在“Agent配置”选择已验证并启用的主模型/摘要模型，检查工具、预算和提示词，保存草稿后发布。已发布配置保持只读，新运行使用发布快照。
5. 按需配置评估模型。在缺少评估模型时，规则检查与模型评分区分展示，不把未知模型分数当作0分。

## 用户最终验收顺序

1. 用户端自动进入→首次选择话题/关键词→保存→刷新恢复同一身份；检查错误时草稿保留、未保存离开、推送时间保存。
2. 管理端确认来源的最后成功/下次采集/周期；手动采集返回排队状态，并等待真实结果。采集失败时保留最后有效快照。
3. 用户端生成简报，管理员查看实际运行事件；确认进度来源于服务端，发布完成前不显示100%，旧简报仍可阅读。
4. 生成完成后检查新闻详情弹窗、原始链接和引用、部分来源缺失、历史搜索/日期筛选/分页；无匹配时允许空结果。
5. 验证每日调度与同一简报的站内发布重试；“已发布”仅表示站内可阅读。没有邮件渠道。
6. 管理端进行固定用例评估，核对数据版本、评分器版本、规则/人工/模型分数的区别；评分不可用保持空值。
7. 检查管理员与匿名身份隔离、封禁/解封审计、429等待提示、移动端重排及键盘弹窗。

缺少模型或搜索凭证时，页面显示真实不可用/未配置结果，不提供模拟成功或假简报。当前没有生产部署；停止本项目使用`docker compose stop`，数据卷保留。实际检查结果以`.project-flow/versions/v1.0.0/`的阶段报告与证据为准。
