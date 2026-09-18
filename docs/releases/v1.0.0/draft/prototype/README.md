# 知更双端交互原型 · r1

v1.0.0 当前处于 ITERATE，未冻结基线。用户要求先提交 DISCOVER 成果（Git `98fd673`），再制作原型，下一轮继续调整原型和方案。本目录与计划中的正式应用源码隔离。

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

两个 Vite 服务均绑定 `127.0.0.1`，端口分别为 5173/5174；端口占用会明确失败，不自动切换。默认已经进入演示状态；登录/注册使用有效格式邮箱和至少 8 位演示密码，不输入真实密码或 API key。

## 建议体验路径

1. 用户端进入兴趣订阅，调整主题或关键词并保存；至少填写其中一类。选择“必须包含”时需添加包含关键词。
2. 返回今日简报，立即生成并查看模拟运行；可以取消，也可等待新一期出现。条目可标记已读，详情保留推荐理由、参考来源和偏好快照。
3. 推送设置可修改时间/时区，保存新邮箱后模拟验证，再测试发送；暂停不影响手动生成。初始简报有失败投递，可重试同一期。
4. 管理员端新增/编辑来源、模拟采集；配置模型并模拟连接测试，再编辑/发布 Agent 草稿。
5. 在运行详情查看工具、摘要和子任务示例。启用并测试评估模型后发起模拟实验，比较固定样例结果。

页顶“交互原型”菜单提供正常、加载、空内容、请求失败、部分完成和无权限场景，以及“重置全部示例”。重置恢复 seed 与固定时钟 `2026-09-18T08:12:00+08:00`，清除当前模拟异步任务和编辑状态。

## 模拟边界

新闻、运行事件、用量、费用、评分和发送结果均为 synthetic。这里没有 HTTP 后端、数据库、实际模型/Agent 执行、Tavily 搜索、RSS/NewsNow 抓取或真实邮件发送。文档外链是参考资料，不证明示例标题为当天真实新闻。语言和摘要深度会保存在偏好中，固定示例正文不会由模型重新撰写。

两个开发端口的 localStorage 按 origin 独立保存，刷新可保留各自状态；一端的修改不会实时影响另一端。刷新会将未结束的内存运行标记为取消，不伪装后台仍在执行。正式双端将对接同一个 FastAPI Gateway，本原型不实现这个 HTTP 连接。

“已提交发送”不代表已送达；“连接测试通过”“评估完成”等提示均描述模拟结果。正在运行的异步场景以浏览器内定时器推进，关闭页面不会继续执行工作。

## 结构与检查

```text
prototype/
  user-web/           用户端 Vue 3 / Vite 项目
  admin-web/          管理员端 Vue 3 / Vite 项目
  shared/             设计样式、共享组件、types、fixtures、mock adapter
  scripts/check-contract.mjs
  package.json        npm workspaces 与统一检查命令
  package-lock.json
```

```powershell
npm run check
npm run check:contract
npm run build
```

`check` 执行 `vue-tsc --noEmit`；`build` 先执行相同类型检查，再构建两个工作区。`check:contract` 读取唯一 OpenAPI 契约，校验 14 个 synthetic 固定样例与实际 `shared/fixtures.ts` seed，并检查操作 ID、简报运行归属和新闻时间关系；当前契约包含 48 schemas、54 操作。这些命令检查原型一致性，不证明后端或生产验收通过。浏览器交互、响应式布局和键盘操作的实际结果在阶段证据中另行记录。

设计规则见仓库 `design.md`；当前页面与候选行为见 [02-ux.md](../spec/02-ux.md)，领域和验收见 [03-domain.md](../spec/03-domain.md)、[05-acceptance.md](../spec/05-acceptance.md)。[contracts/openapi.json](../contracts/openapi.json) 为唯一交换主源，[契约说明](../contracts/README.md)记录内存方法到未来 HTTP 的映射与未定事项；共享开发接口见 [shared/API.md](shared/API.md)。
