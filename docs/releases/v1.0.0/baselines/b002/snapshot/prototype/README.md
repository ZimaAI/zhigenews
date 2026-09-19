# 知更双端交互原型 · r5

v1.0.0 / ITERATE，未冻结基线，正式应用尚未实施。原型历史r1=`2bfb26d`、r2=`72b512a`、r3=`e7251f3`；本轮保留r4未提交视觉调整，继续按反馈修改，不进行Git提交。

用户端保持简洁阅读风格和绿色按钮/图标/标签。r5自动匿名进入、删除已读未读和整理记录；单条新闻以弹窗展示详情；生成只显示进度条与预计剩余时间。欢迎页恢复r2视觉，仅用于自动进入、加载、失败重试和旧登录链接，无邮箱/密码/注册表单。管理员独立登录，增加匿名账户监测、配额和封禁。

## 启动

在此目录安装锁定依赖，分别启动两个开发终端：

```powershell
cd D:\Develop\Projects\zhigenews\docs\releases\v1.0.0\draft\prototype
npm ci
npm run dev:user
```

```powershell
npm run dev:admin
```

- [用户端](http://127.0.0.1:5173/today)：首次自动创建匿名Cookie会话并引导话题/背景/关键词；已完成的相同Cookie直接阅读。
- [管理员端](http://127.0.0.1:5174/overview)：独立管理员演示登录，查看匿名账户与运行监测。

Vite仅绑定127.0.0.1，固定5173/5174且端口占用时报错。静态dist/preview不包含Cookie模拟服务。**两个开发服务都需要启动**，管理员匿名监测代理到用户端的开发服务。管理员使用页面给出的演示凭据，不输入真实密码或API key。

## 体验路径

1. 首次进入自动建号 → 保存话题或关键词 → 今日；刷新验证同一Cookie保持身份与引导状态。
2. 更新简报，观察进度条/预计时间或“正在估算”；生成时旧内容保持可读，完成后打开结果，不显示工具和阶段日志。
3. 点击新闻标题或阅读详情打开单条弹窗，查看推荐理由/引用；Esc关闭恢复焦点，来源外链可单独打开。没有已读未读、仅未读过滤或整理记录。
4. 头像进入个人设置，只编辑三项偏好和每日推送时间；试验未保存离开/失败重试。
5. 管理端查看匿名账户、计数、风险与事件；修改有效配额，封禁后用户新请求被拒绝，解除后仍受限额约束。保留来源、模型、Agent配置、运行、评估及站内发布重试。

原型菜单仍有正常、加载、空、失败、部分完成和无权限场景。场景切换/重置只影响示例交互，不能作为清Cookie或重置IP配额的手段。新闻seed参考时钟为2026-09-18T08:12:00+08:00，匿名HTTP请求时间使用实际服务器时间。

## 模拟边界

r5新增 `shared/demo-server.ts` 的开发专用 `/__demo` 服务，真实演示服务器Set-Cookie（HttpOnly/SameSite=Lax）、会话恢复、计数、限流和封禁。生产HTTPS才启用Secure。用户5173与管理员5174通过该服务共享匿名监测，管理员使用独立演示Cookie；会话token只存哈希，数据存储于被Git忽略的 `.demo` 本地文件。

用户偏好/新闻/设置仍在浏览器按匿名身份隔离保存，其他管理业务使用集中mock。Cookie丢失意味着新身份，不能靠旧缓存冒充同一账号。开发服务的生成进度根据演示时钟估算，没有实际模型或Agent后台执行。

新闻、Agent事件、用量、费用、评分和站内发布结果均为synthetic；没有正式FastAPI/MySQL/Redis安全实现、真实RSS/NewsNow/Tavily采集或每日定时推送。参考外链不证明当天发生示例新闻。生产会话、归属、原子限额、代理信任和故障恢复须在后端阶段重新验收。当前事件记录封禁/解封与限流，正式策略修改的管理员审计仍待后端实施。

## 结构与检查

```text
prototype/
  user-web/               用户端与独立主题
  admin-web/              管理员端
  shared/                 类型、fixtures、mock与语义组件
    anonymous.ts          开发HTTP客户端
    demo-server.ts        仅本地Vite服务
  scripts/check-contract.mjs
```

```powershell
npm run check
npm run check:contract
node scripts/check-anonymous.mjs
npm run build
```

check为vue-tsc，build先类型检查再构建双端；check:contract校验50 schemas、52操作、22份synthetic固定样例及实际seed/public投影，验证移除字段和内部运行数据不能进入公开响应、管理员独立认证。check-anonymous使用临时本地服务验证Cookie、身份恢复、角色/CSRF隔离、并发去重、配额、封禁/解封与重启；不修改日常演示数据。它们不等于正式后端通过；浏览器、Cookie/限额及弹窗的实际结果以阶段证据为准。

设计见根目录 [design-user.md](../../../../../design-user.md) 3.2和[design.md](../../../../../design.md) 2.2；候选行为见[02-ux.md](../spec/02-ux.md)，领域/安全依据/验收见spec其余章节。[OpenAPI](../contracts/openapi.json)是唯一正式交换主源；[shared/API.md](shared/API.md)记录原型开发接口和正式API的区别。仍在ITERATE，可继续修改。
