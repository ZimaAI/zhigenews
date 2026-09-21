# 准备本机生产部署

Type: task
Status: resolved
Blocked by: none

实现可选 Nginx 入口模式，验证代理和生产 Compose，生成本机密钥与初始化材料，记录剩余人工步骤。

## Comments

本机 Ubuntu 24.04 / amd64，Compose 5.3.1；Nginx 已有站点占用 80/443。
当前用户无 Docker socket 权限，sudo 需要交互密码；没有 gh、业务 .env 或 GHCR 登录。

## Answer

已加入可选 Nginx Compose 覆盖、HTTP Caddy 配置、Nginx 示例和部署脚本支持；默认直接 HTTPS 模式保持可用，运维和备份文档已同步。
9 项部署测试通过；真实 Nginx/Caddy 临时进程验证了双域名、SPA、客户端 IP、防伪造转发头和 SSE。Caddy 配置与 Bash 语法检查通过。
部署配置、随机密钥、专用 SSH 密钥、主机记录及需要 sudo 的初始化脚本已生成到仓库外受限目录 `/home/zima/.local/share/zhigenews-deploy/`，完整交接见该目录 HANDOFF.md。
用户已确认管理端域名及邮箱。公网 36.151.151.229:22 的 SSH 主机公钥与本机匹配；Snap Certbot 续期定时器正常。
尚未安装系统配置、构建 Docker 镜像、申请证书或上线；仓库修改尚未提交推送。
