# 部署配置与指导

Type: task
Status: resolved
Blocked by: none

实现生产 Compose、前端镜像、Actions、部署脚本与中文文档，并验证构建、配置及关键部署顺序。

## Comments

- 默认 Ubuntu 24.04、Docker Compose 2.30+、两个域名、GHCR 和 SSH；当前分支为 main。

## Answer

已实现 `.github/workflows/deploy.yml`、`infra/deploy/` 与 `docs/deployment.md`，并添加 README 入口。生产配置与开发编排独立，覆盖镜像 digest、SSH、HTTPS、持久化、单次初始化、迁移前数据库备份和失败处置。

验证结果（2026-09-21）：

- 前端、后端 Docker 镜像构建成功；前端契约与类型检查、9 项 API 客户端测试通过。
- actionlint、ShellCheck、Bash 语法检查通过。
- 6 项 Linux 部署脚本测试通过，覆盖首次上线、更新备份和拉取/备份/迁移/HTTPS 失败；Docker 和 curl 为模拟命令。
- 生产 Compose 配置解析通过；实测 raw 环境文件在容器中保留 `$` 与 `#`，Origin、代理白名单和内部服务端口符合预期。
- Caddy 配置验证通过；实际前端镜像连接模拟 API，验证双站点、深层路由、API 转发及查询参数、404、缓存头。临时容器、网络、卷已清理。
- 没有向 GHCR 发布镜像，没有连接真实服务器；公网证书、实际数据库升级和真实模型/Tavily 生成待配置服务器后验收。不变更产品阶段。
