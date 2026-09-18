# v1.0.0 续接入口

当前 v1.0.0 / ITERATE / 原型 r3，未冻结。按用户要求先提交 r2 为 72b512a；本轮极简界面、三字段偏好、时间唯一设置和首次引导修改留在工作区。

续接命令：python .agents/skills/prototype-to-product/scripts/version_flow.py resume --root . --version v1.0.0

先读对应设计规范：用户 design-user.md，管理员 design.md。用户仅今日/历史主导航，头像直达个人设置；偏好只有话题/背景/关键词，推送只有每日时间，仅站内。首次完成标记持久化；旧偏好与推送路由兼容跳转。管理员保留侧栏控制台，站内通知重试语义已同步。

原型说明：docs/releases/v1.0.0/draft/prototype/README.md。用户 http://127.0.0.1:5173/，管理员 http://127.0.0.1:5174/overview。prototype 目录分别运行 npm run dev:user / npm run dev:admin，旧端口进程和浏览器句柄不是可移植状态。

证据：evidence/prototype-r3-validation.json。构建、类型、契约、核心浏览器流程与 18 组布局检查通过。当前契约 47 schemas / 51 操作 / 14 样例，领域和验收仍为候选；没有真实后端或站内定时执行。双端 localStorage 独立，新 r3 键清除旧邮件偏好影响。

下一动作：根据新反馈继续 ITERATE。明确要求定稿后再处理 SPECIFY；当前无阶段推进问题，不自动冻结或开发正式后端。
