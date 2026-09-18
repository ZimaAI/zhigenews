# v1.0.0 续接入口

当前：v1.0.0 / 未冻结 / ITERATE / 原型 r1。DISCOVER 已按用户要求提交为 `98fd673`；原型与契约新修改留在工作区。没有候选基线、后端交接或正式实现批准。

先运行：

```powershell
python .agents/skills/prototype-to-product/scripts/version_flow.py resume --root . --version v1.0.0
```

入口：`docs/releases/v1.0.0/draft/prototype/README.md`。用户端 http://127.0.0.1:5173/today，管理端 http://127.0.0.1:5174/overview。如服务已退出，在 prototype 目录分别执行 `npm run dev:user` 和 `npm run dev:admin`；依赖缺失先 `npm ci`。端口/PID 不作为可移植状态。

原型覆盖用户订阅、阅读、历史、推送设置与生成/取消；管理员来源、模型、配置版本、运行观察、评估、用户、投递。数据与工具执行全部模拟，双端本地存储独立。参见 spec/02-ux.md、03-domain.md、05-acceptance.md、唯一契约 contracts/openapi.json；技术依据为 docs/research/ 三份文档。

真实验证见 `evidence/prototype-validation.json`：类型检查、双端构建、契约/seed 与浏览器关键流程通过；未验证真实后端、模型、采集、MySQL、Tavily 或邮件。34 条 AC 是未来验收定义，没有标记生产通过。

用户原话：“先提交，然后实现原型，我会在下一个阶段中调整原型和方案”。q0001 已处理；没有待回答的阶段推进问题。下一动作：继续本版 ITERATE，按用户反馈修改原型、领域、契约、样例、验收并递增 revision，不重做 DISCOVER，不自动冻结规范或写正式后端。
