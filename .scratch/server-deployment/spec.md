# GitHub Actions 服务器部署

为当前正式应用提供单机 Linux x86_64 部署：Actions 构建并发布 GHCR 镜像，SSH 更新 Docker Compose，Caddy 为双域名提供 HTTPS。业务密钥留在服务器；保留本地开发编排。覆盖迁移、首次初始化、持久化、健康检查、备份及回退说明。不执行真实服务器上线，不改变产品验收阶段。
