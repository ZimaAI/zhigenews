# 知更双端交互原型 · r3

v1.0.0 当前处于 ITERATE，未冻结基线。DISCOVER 成果已提交（Git `98fd673`），原型 r1 提交为 `2bfb26d`；本轮修改前已提交 r2（Git `72b512a`）。r2 按截图改版并拆分设计规范；本轮 r3 尚未提交，按最新反馈简化用户端、仅保留三项订阅偏好和站内每日时间，增加首次引导。仍可继续调整原型和方案。本目录与计划中的正式应用源码隔离。

## 本轮视觉调整

用户端遵循根目录 [design-user.md](../../../../../design-user.md)：浅冷灰外背景、白色画布、绿色强调和简洁导航。首次进入 [用户端](http://127.0.0.1:5173/today) 会引导设置话题、背景、关键词；保存后开始阅读。头像直接进入个人设置，偏好仅三字段，推送仅每日时间。原来的 `/preferences` 和 `/delivery` 兼容跳转到设置子页。

管理员端遵循根目录 [design.md](../../../../../design.md)，继续使用原深青绿、暖白、侧栏、表格及运行监测风格。用户主题和壳在 `user-web/` 中独立加载，共享基础组件、类型及 mock adapter 保持双端可用。

## 启动

在已安装 Node.js/npm 的环境中，从本目录安装锁定依赖：

```powershell
cd D:\Develop\Projects\zhigenews\docs\releases\v1.0.0\draft\prototype
npm ci
```

分别在两个终端运行：

```powershell
npm run dev:user
```

```powershell
npm run dev:admin
```

- 用户端：[今日简报](http://127.0.0.1:5173/today)，独立项目 `user-web/`。
- 管理员端：[管理概览](http://127.0.0.1:5174/overview)，独立项目 `admin-web/`。

两个 Vite 服务均绑定 `127.0.0.1`，端口分别为 5173/5174；端口占用会明确失败，不自动切换。默认使用已登录演示身份，首次偏好尚未完成；登录/注册使用有效格式邮箱和至少 8 位演示密码，不输入真实密码或 API key。

## 建议体验路径

1. 首次进入填写话题或关键词，可补充背景；保存后进入今日，刷新不会重复引导。
2. 点击头像进入个人设置，只编辑三项偏好或每日推送时间；尝试未保存离开、失败后重试。
3. 返回今日生成模拟简报，可取消或等待完成。模拟筛选取最近 24 小时内命中任一所选话题或任一关键词的内容，最多 10 条；无匹配不凑数，背景仅保存供正式 Agent 使用。条目可标记已读，详情保留推荐理由与参考来源；系统仅发布站内简报。
4. 管理端新增/编辑来源、模拟采集；配置并模拟测试模型，编辑/发布 Agent 草稿。
5. 查看运行工具/摘要/子任务，比较固定样例实验，重试站内发布故障。

页顶原型菜单提供正常、加载、空内容、请求失败、部分完成和无权限场景，以及“重置全部示例”。场景切换清除模拟异步任务并恢复其他示例数据，保留已保存偏好和首次完成标记；“重置全部示例”恢复 seed 与固定时钟 `2026-09-18T08:12:00+08:00`，清空首次完成标记并重进引导。

## 模拟边界

新闻、运行事件、用量、费用、评分和发送结果均为 synthetic。这里没有 HTTP 后端、数据库、实际模型/Agent 执行、Tavily 搜索、RSS/NewsNow 抓取或真实站内定时发布。文档外链是参考资料，不证明示例标题为当天真实新闻。窗口 24 小时、最多 10 条、全部来源等是内部演示默认值，固定正文不经模型改写。

两个开发端口的 localStorage 按 origin 独立保存，刷新可保留各自状态；一端的修改不会实时影响另一端。刷新会将未结束的内存运行标记为取消，不伪装后台仍在执行。正式双端将对接同一个 FastAPI Gateway，本原型不实现这个 HTTP 连接。

站内“已发布”不代表用户已阅读；“连接测试通过”“评估完成”等提示均描述模拟结果。正在运行的异步场景以浏览器内定时器推进，关闭页面不会继续执行工作。

## 结构与检查

```text
prototype/
  user-web/           用户端 Vue 3 / Vite 项目、独立主题与布局
  admin-web/          管理员端 Vue 3 / Vite 项目
  shared/             管理默认样式、共享原语、types、fixtures、mock adapter
  scripts/check-contract.mjs
  package.json        npm workspaces 与统一检查命令
  package-lock.json
```

```powershell
npm run check
npm run check:contract
npm run build
```

`check` 执行 `vue-tsc --noEmit`；`build` 先执行相同类型检查，再构建两个工作区。`check:contract` 读取唯一 OpenAPI 契约，校验 14 个 synthetic 固定样例与实际 `shared/fixtures.ts` seed，并检查操作 ID、简报运行归属和新闻时间关系；当前契约包含 47 schemas、51 操作。这些命令检查原型一致性，不证明后端或生产验收通过。浏览器交互、响应式布局和键盘操作的实际结果在阶段证据中另行记录。

用户与管理员设计规则分别见根目录 [design-user.md](../../../../../design-user.md)、[design.md](../../../../../design.md)；当前页面与候选行为见 [02-ux.md](../spec/02-ux.md)，领域和验收见 [03-domain.md](../spec/03-domain.md)、[05-acceptance.md](../spec/05-acceptance.md)。[contracts/openapi.json](../contracts/openapi.json) 为唯一交换主源，[契约说明](../contracts/README.md)记录内存方法到未来 HTTP 的映射与未定事项；共享开发接口见 [shared/API.md](shared/API.md)。
