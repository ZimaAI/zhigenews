# v1.0.0 实现完成 · 用户最终验收

当前为 **v1.0.0/b003 / FRONTEND_VERIFY / 后端 h001**。后端与双端正式应用均已实现；用户明确要求在全部实现后自己测试验收，因此当前交付的是可运行代码与开发检查结果，未将完整系统验收或真实外部服务标为通过。没有待确认问题，也不再因缺模型密钥阻塞前端。

用户原话：“确认当前后端的验收进入到前端实现。我会在整个项目实现完成之后自己进行测试验收”。此前版本范围内无需逐阶段确认的授权仍保留。

## 运行入口

- 用户端：http://127.0.0.1:5173，自动匿名Cookie；正式源码 apps/user-web。
- 管理端：http://127.0.0.1:5174，使用 backend/.env 的管理员账户；正式源码 apps/admin-web。
- API：http://127.0.0.1:18000/api/v1；健康 /healthz。MySQL13316、Redis56386；Docker API/worker/beat已运行。
- 完整启动与最终验收步骤：docs/releases/v1.0.0/IMPLEMENTATION.md。
- 根目录 npm ci；npm run dev:user / dev:admin；npm run build 生成两端 dist。

## 身份与证据

基线manifest：edf798f08091b75c179a714eb6d488aa3868271f9566bed47b057ca39c00c05c。
后端指纹：64fd2c11f1b643bc0a53615de685626d303f55c735d7254d7f8e20548b9e42f0。
h001 manifest：75bca791c20f71161f7c9ecacb0997aa807fa0ea907eb47c5dd017e0865da136。
前端指纹：bafd33fbd87cff395a55ab8a46541c796be1a7a752b92cfb39c4117e7624a0f0。
仓库起点994e069c0cb3b688248efd3deb7ec0bc1fd522b0；改动未提交、未推送，未部署生产。

原有后端121项测试通过；当前 h001 live source 再核验通过。前端API客户端9项测试通过；53操作/52DTO生成一致；根类型检查、用户端及管理员端独立生产构建通过。详见 frontend-verification.json、evidence/frontend-developer-checks.json、frontend-build.txt、frontend-user-browser.json、frontend-admin-browser.json。

实际浏览器检查覆盖匿名引导/刷新、偏好与每日时间持久化、未保存离开、真实配置缺失错误、历史空/搜索空、管理员登录/真实来源、评估用例保存/刷新、配额校验、移动菜单与响应式。完整成功/partial生成、真实新闻弹窗、实时运行/LLM评估/投递重试和完整错误矩阵没有假报通过。

临时管理员和临时评估用例已经删除；开发检查创建的匿名读者仍保留偏好与09:15时间，便于继续查看。未创建假模型、假简报或假运行，未变更真实来源及防护策略。

## 下一步

由用户配置模型/Tavily，在正式两端进行最终业务验收；按 IMPLEMENTATION.md 记录问题。先运行公开 resume，再读本文件和 frontend-verification.json，不从旧c0009的后端阻塞重新开始。前端缺陷在本阶段修复；后端缺陷按 reopen-backend 重新交接；不修改冻结 b003/h001。实际必需检查完成后才推进INTEGRATION_VERIFY/DELIVERED，不能把本次开发构建当作全系统验收。

```powershell
uv run --project backend python .agents/skills/prototype-to-product/scripts/version_flow.py resume --root . --version v1.0.0
```
