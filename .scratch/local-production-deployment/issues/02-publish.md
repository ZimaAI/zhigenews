# 安装本机配置并发布

Type: task
Status: open
Blocked by: 01

## Comments

等待用户补全仓库外 backend.env 中的模型/Tavily 凭据，执行 prepare-host.sh（sudo 需要交互密码），配置管理端 DNS，使用现有 Certbot 为新域名签发证书，以及配置 GHCR 登录和 GitHub production Secrets。
完成后提交/推送部署修改，观察 Actions 发布，检查 HTTPS、登录和真实生成。不能把准备和临时 synthetic 验证当成生产上线成功。

2026-09-21 后续核对：deploy SSH 登录、Docker 权限、安装后的业务配置必填字段均通过。已发布的 backend GHCR 镜像可匿名读取，无需额外登录。
公共 DNS（Google DNS）仍返回 admin.zhigenews.zimagent.top NXDOMAIN；用户端 TLS 主机名不匹配，Nginx 知更站点仍只配置 HTTP。
GitHub 上一次运行 35573117510 在前端构建失败；本机 npm run check:contract 复现，生成文件指纹未跟随后端契约更新，已运行 generate:api 修复。双前端构建、9 项 API 测试和 9 项部署测试通过。
git push --dry-run 因没有 GitHub HTTPS 凭据失败。待用户完成 DNS、证书及 Git 推送认证，再继续发布与线上验收；当前没有运行中的知更生产容器。
