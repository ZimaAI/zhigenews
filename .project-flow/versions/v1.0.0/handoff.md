# v1.0.0 续接入口

当前 v1.0.0 / ITERATE / 原型 r2，未冻结。原型 r1 已按用户要求先提交为 `2bfb26d`；本轮用户端视觉改版与规范拆分留在工作区。

```powershell
python .agents/skills/prototype-to-product/scripts/version_flow.py resume --root . --version v1.0.0
```

用户规范 `design-user.md`，管理员规范 `design.md`。用户端为白色画布、绿色顶部导航、主题搜索/封面卡片；管理员保留原深青绿侧栏控制台。先看 [原型说明](../../../docs/releases/v1.0.0/draft/prototype/README.md)；实际相对仓库路径为 docs/releases/v1.0.0/draft/prototype/README.md。

运行入口：http://127.0.0.1:5173/preferences 与 http://127.0.0.1:5174/overview。若服务停止，prototype目录 npm ci 后分别 npm run dev:user / npm run dev:admin。端口和旧浏览器句柄不是可移植状态。

验证记录：evidence/prototype-r2-validation.json；历史r1证据保留。规范、契约和领域仍为草稿，双端使用独立localStorage和模拟数据。本轮无HTTP契约变化、无真实后端执行。

下一动作：按用户反馈继续ITERATE；明确要求定稿后再处理SPECIFY阶段确认。当前没有待回答的阶段推进问题，不自动冻结或实现正式后端。
