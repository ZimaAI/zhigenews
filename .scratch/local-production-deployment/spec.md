# 本机生产部署

将知更部署到 zhigenews.zimagent.top，管理端暂定 admin.zhigenews.zimagent.top。
保留宿主 Nginx 及已有站点，通过仅绑定回环的 Caddy 容器提供双前端和 API。
复用 GitHub Actions、生产 Compose 和数据库备份/迁移流程。
自动完成可执行准备，密钥只存仓库外受限目录；sudo、DNS、GitHub 权限和业务凭据缺失时明确交接。
