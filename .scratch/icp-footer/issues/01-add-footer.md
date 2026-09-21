# 添加备案号

Type: task
Status: resolved
Blocked by: none

同步用户端设计规范，在阅读框架和匿名欢迎页添加备案链接，验证构建后提交推送。

## Answer

- 已拉取 origin/main 最新代码，并在用户端阅读框架和匿名欢迎页复用 IcpLink，展示指定备案号并链接工信部网站。
- 已同步 design-user.md；链接提供新标签提示、44px 点击高度和键盘焦点。
- `npm run build:user`（含 vue-tsc 类型检查）与 `git diff --check` 通过。
- 未运行浏览器视觉检查或完整业务流程回归。
