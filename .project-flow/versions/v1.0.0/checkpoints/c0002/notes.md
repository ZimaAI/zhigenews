# v1.0.0 · ITERATE r1 续接笔记

## 用户意图与授权

用户：“先提交，然后实现原型，我会在下一个阶段中调整原型和方案”。已先将前轮 DISCOVER 成果提交为 `98fd673`（`docs: capture v1.0.0 discovery and agent research`），未推送。随后 answer-review q0001，DISCOVER → ITERATE；state 保留真实原话。原型代码尚未提交，未取得具体基线或正式前后端批准。

## 本轮产物

- 原型 r1：docs/releases/v1.0.0/draft/prototype/ 下独立 user-web/admin-web；Vue 3、TypeScript、Vite、Router、Lucide，npm workspaces。已读 design.md 全文，共享其变量与组件。
- 用户端：今日/详情/历史、兴趣与记忆、推送与邮箱、首次引导、登录注册、运行详情、手机设置与导航。
- 管理端：概览、来源/详情、模型端点、配置草稿与发布、运行/trace/取消、评估样例与 A/B、用户与投递。
- 共享 mock adapter、synthetic seed、可重置状态与固定时钟。没有真实后端或第三方调用；两端 origin 的 localStorage 独立。
- 领域、唯一 OpenAPI 3.1 契约（54 operations/48 schemas）、14 固定样例、34 AC 与 23 REQ 双向关联；仍为候选规范。
- 根 AGENTS.md 保留 CodeGraph 规则、明确前端读取 design.md；.gitignore 排除构建产物与依赖。

## 真实验证及修正

完整记录在 evidence/prototype-validation.json。最终 npm run check:contract 与 npm run build 退出 0，类型检查与双端 Vite 构建通过。

用 Codex In-app Browser 操作两个本地服务，检查订阅保存/生成4条、已读、失败投递同一期重试、错误保存保留输入并重试成功、配置发布只读、启用评估模型/新实验/指标对比、取消运行后无新产物、空内容和无权限状态、重置、手机弹窗 Escape 与焦点返回。320/375/768/1024/1440/1920 的今日与运行详情无整页溢出；320 额外覆盖设置、来源、模型、配置、评估、概览。截图在工具会话内观察，未导出 PNG。最终浏览器 error 日志为空。

发现且修正：已读对象共享导致多次切换；历史条目时间与归属；新简报摘要/事件条数与筛选一致；纯关键词订阅阻塞；错误恢复时 loading 分支销毁表单导致输入丢失（现隐藏保留组件）；未验证邮箱重试；发布前模型校验；重复版本与只读发布；来源地址变更后重新验证。

浏览器评估启动后自动跳转详情，旧列表定位超时，改用当前页面入口；details 语义定位不一致，读取 DOM 后使用已知菜单选择器。首次失败保存恢复后的输入检查失败，修复 Shell 后重跑确认值7保留且版本4保存成功。一次文档补丁含同路径删除/新增被拒，随后改为单次更新。doctor 命令不支持 --version，改为 doctor --root . 后通过；无 repairs。git diff --check 通过。不存在尚未修复的已观察阻塞。

## 状态与下一动作

保持 ITERATE，prototype_revision=1，未 seal/approve/进入 SPECIFY。用户将审阅并调整原型与方案；明确要求定稿之后再处理阶段确认。不把可点击模拟视为 Agent/数据库/沙箱集成已经实现。

本轮服务：5173 用户端、5174 管理端；若退出，按 prototype/README.md 重启。不要依赖旧浏览器句柄或进程。保留工作区修改。检查点从 c0001 推进 c0002，以 state 和 RESUME.md 为准。

续接提示：继续 v1.0.0 ITERATE，先 resume，然后按用户反馈修改原型和方案；不新建版本、不重新研究既定需求、不推进正式后端。
