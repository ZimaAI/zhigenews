# v1.0.0 续接入口

当前 ITERATE r5，未冻结，main/e7251f3；本轮及前轮修改未提交。

运行 python .agents/skills/prototype-to-product/scripts/version_flow.py resume --root . --version v1.0.0，按返回入口续接。用户设计design-user.md 3.2，管理设计design.md 2.2。

r5用户自动匿名Cookie会话；欢迎页为原r2视觉但无凭据表单；三字段偏好/每日时间/首次引导保留。已读未读和用户Agent记录全部移除，单条新闻弹窗，总体进度和预计剩余时间。管理员独立演示会话，/users监测真实dev匿名账号和配额、风险、封禁审计；实际Agent事件只在管理员原型中。

从 docs/releases/v1.0.0/draft/prototype 同时运行 npm run dev:user 和 npm run dev:admin。用户 http://127.0.0.1:5173/today，管理 http://127.0.0.1:5174/users。5174代理5173的/__demo服务；静态dist没有Cookie接口。会话与计数在ignored .demo/anonymous.json，浏览器偏好按匿名ID本地隔离；生产后端和真实生成仍待实现。

证据 evidence/prototype-r5-validation.json；构建、类型、契约、独立Cookie/限流检查、相关浏览器交互和24组布局均通过。共享Modal已修正Tab首尾循环。24REQ/36AC、50schemas/52操作/22样例。

下一动作：按反馈继续ITERATE r5，无待确认阶段推进问题；不自动进入SPECIFY或正式后端。
