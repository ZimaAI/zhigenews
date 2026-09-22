# 使用 GitHub Actions 部署到服务器

本方案部署正式用户端、管理端和后端，适用于一台 **Linux x86_64 服务器**。默认使用 Ubuntu 24.04、Docker Engine、Compose 插件 **2.30+**、两个域名和 GitHub Container Registry（GHCR）。服务器只拉取镜像，无需安装 Node.js、uv 或检出仓库。ARM 服务器需调整工作流的构建平台后再使用。

部署会短暂停止 API 和后台任务，再执行迁移与重启；已有任务的 worker 最多等待 12 分钟退出。它不是零停机发布。真实模型、Tavily 和最终业务验收仍需按 [实现与验收入口](releases/v1.0.0/IMPLEMENTATION.md) 验证。

## 1. 文件与访问方式

| 文件 | 作用 |
| --- | --- |
| [.github/workflows/deploy.yml](../.github/workflows/deploy.yml) | main 推送或手动触发，构建、发布镜像，再通过 SSH 部署 |
| [infra/deploy/compose.yaml](../infra/deploy/compose.yaml) | 独立生产编排，项目名固定为 `zhigenews-prod` |
| [infra/deploy/web.Dockerfile](../infra/deploy/web.Dockerfile) | 构建两个正式前端，运行 Caddy |
| [infra/deploy/Caddyfile](../infra/deploy/Caddyfile) | 双域名 HTTPS、SPA 路由、同源 API、SSE 转发 |
| [infra/deploy/deploy.sh](../infra/deploy/deploy.sh) | 拉取、校验、备份、迁移、初始化、启动和健康检查 |
| [infra/deploy/.env.example](../infra/deploy/.env.example) | 服务器基础设施配置模板 |
| [infra/deploy/backend.env.example](../infra/deploy/backend.env.example) | 服务器业务密钥模板 |

默认流量路径：浏览器 → Caddy（80/443）→ 用户端或管理端静态文件；两个域名的 `/api/*` 和 `/healthz` 均转发到内部 API。MySQL、Redis、API 没有宿主机端口。管理端仍使用应用自己的管理员登录。

Caddy 负责证书申请和续期；SSE 使用即时转发。浏览器使用 HTTPS Secure Cookie，生产 Origin 白名单由两个域名生成。API 保留代理的原始连接地址，由应用只信任固定 Caddy IP，避免所有用户共享代理 IP 的限流额度。

## 2. 准备服务器和域名

建议起步 4 vCPU / 8 GB 内存 / 40 GB 磁盘，按来源数量、并发和数据保留时间调整。需要服务器能访问 GHCR、Docker Hub、模型接口、Tavily 和新闻源；GitHub 托管 runner 必须能 SSH 到服务器。

1. 按 [Docker 官方 Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/) 安装 Docker Engine 和 Compose 插件。确认 `docker version` 和 `docker compose version` 可用，Compose 至少 2.30（使用 raw env_file）。
2. 将 `news.example.com` 和 `admin.example.com` 的 A 记录指向服务器。若设置 AAAA，IPv6 也必须可达。首次部署建议 DNS 直连服务器；已有 CDN 或上游代理需要另行调整可信代理规则。
3. 云安全组与服务器防火墙开放 TCP 80、443、SSH 端口；UDP 443 可用于 HTTP/3。不要开放 3306、6379、8000。80/443 不能已有其他服务占用。
4. 创建专用部署账号（以下由具备 sudo 权限的账号执行）：

```bash
sudo adduser --disabled-password --gecos '' deploy
sudo usermod -aG docker deploy
sudo install -d -o deploy -g deploy -m 700 /opt/zhigenews
sudo install -d -o deploy -g deploy -m 700 /home/deploy/.ssh
```

在自己的电脑生成独立密钥 `ssh-keygen -t ed25519 -f zhigenews-deploy`，用于无人值守部署时不设置口令。把 `.pub` 内容写入服务器 `/home/deploy/.ssh/authorized_keys`，设权限 600、所有者 deploy。私钥保留给 GitHub Secret，禁止提交仓库。重新登录 deploy 后验证 `docker ps`。

部署账号的 Docker 权限及 worker 的 Docker socket 可控制宿主机，应只授予可信维护者。socket 只挂载给 worker，不挂载给 API、前端或 Agent 沙箱。

以下服务器命令均用 **deploy 账号**执行，除非明确标注 sudo。

### 已有 Nginx 占用 80/443 的服务器

宿主机已有其他站点时保留 Nginx，用可选覆盖文件将项目入口限制到回环地址：

```bash
sudo install -o deploy -g deploy -m 600 infra/deploy/compose.nginx.yaml /opt/zhigenews/compose.override.yaml
```

`deploy.sh` 自动合并此文件；未安装覆盖文件的服务器继续由容器 Caddy 直接提供 HTTPS。覆盖文件使用 Compose `!override` 完整替换端口列表，web 只发布 `127.0.0.1:18080:80`，不会保留默认 TCP/UDP 443。web 镜像同时包含 HTTP 专用的 `Caddyfile.nginx`。

1. `.env` 设置两个真实域名，例如 `USER_DOMAIN=zhigenews.zimagent.top`、`ADMIN_DOMAIN=admin.zhigenews.zimagent.top`。两者都需 DNS 解析到本机。
2. 将 [nginx.conf.example](../infra/deploy/nginx.conf.example) 安装到 `/etc/nginx/sites-available/zhigenews`，按实际域名调整，软链接到 `sites-enabled`，通过 `sudo nginx -t` 后 reload。
3. DNS 和公网 80 可达后运行 `sudo certbot --nginx -d zhigenews.zimagent.top -d admin.zhigenews.zimagent.top --redirect`，由宿主 Nginx 处理证书和续期。确认 Certbot 的自动续期任务正常。
4. 再触发 Actions；部署脚本仍检查两个公网 HTTPS 入口。容器启动前 Nginx 返回 502 是预期现象。

Nginx 覆盖客户端传入的 `X-Forwarded-For`，Caddy 只信任固定 Docker 网关（默认 `172.30.0.1/32`），向 API 转发解析后的单一客户端 IP。API 仍只信任 Caddy 的固定地址。Nginx 关闭缓冲，Caddy 即时转发，保留 SSE 更新；生产 Cookie 和 Origin 继续使用 HTTPS。

网段冲突时同步调整 `.env` 的 `DOCKER_SUBNET`、`DOCKER_IP_RANGE`、`DOCKER_GATEWAY`、`CADDY_IP`、`TRUSTED_PROXY_CIDRS`；网关须处于子网中、动态地址池外，且与 Caddy IP 不同。此模式需要支持上述配置的新版 web 镜像，不能用覆盖文件启动尚未包含 `Caddyfile.nginx` 的旧镜像。

## 3. 配置服务器密钥

把两个模板复制到服务器（可从本地 scp）：

```bash
scp infra/deploy/.env.example deploy@SERVER:/opt/zhigenews/.env
scp infra/deploy/backend.env.example deploy@SERVER:/opt/zhigenews/backend.env
```

在服务器编辑它们并执行：

```bash
chmod 600 /opt/zhigenews/.env /opt/zhigenews/backend.env
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 24
docker run --rm python:3.12-slim python -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

前四行随机值分别用于 MySQL 应用密码、MySQL root 密码、`IP_HASH_KEY`、管理员密码；最后一行为 `SECRET_ENCRYPTION_KEY`。每项单独生成，妥善保管。

`.env` 必填：

| 字段 | 填写方式 |
| --- | --- |
| `USER_DOMAIN` / `ADMIN_DOMAIN` | 两个不同的裸域名，不带 `https://` 或路径 |
| `ACME_EMAIL` | 证书维护邮箱 |
| `MYSQL_PASSWORD` / `MYSQL_ROOT_PASSWORD` | 上述独立十六进制随机密码；应用密码拼接进数据库 URL |
| `DOCKER_SUBNET` / `DOCKER_IP_RANGE` / `CADDY_IP` / `TRUSTED_PROXY_CIDRS` | 默认保持模板值；与现有 Docker/VPN 网段冲突时一起调整。动态地址池须位于 subnet 内且不包含 Caddy IP，可信代理只填 Caddy 的 `/32` 地址 |
| `SANDBOX_IMAGE` | 默认保持模板固定 digest；部署时会提前拉取，沙箱启动无需临时下载 |

`backend.env` 必填：`SECRET_ENCRYPTION_KEY`、`IP_HASH_KEY`（至少 32 字符）、`ADMIN_EMAIL`、`ADMIN_PASSWORD`（至少 12 字符）、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY`、`TAVILY_API_KEY`。

`backend.env` 使用 **raw** 格式：写 `KEY=value`，不在值外包引号、不写行尾注释；`$` 和 `#` 可以直接作为密码内容。生产数据库、Redis、运行目录、Cookie 和 Origin 由 Compose 设置，不从此文件覆盖。可按 [后端模板](../backend/.env.example) 追加摘要模型配置；LangSmith 默认关闭，需要时配置后开启。

`SECRET_ENCRYPTION_KEY` 必须与数据库一起长期保存，丢失或更换会导致已有加密凭据和任务快照无法解密。已初始化数据库的 MySQL 密码不会随 `.env` 自动修改；改密码需要先在数据库中变更。管理员只在首次初始化时创建；修改 `ADMIN_PASSWORD` 不会重置已有账号。

## 4. 授权服务器拉取 GHCR 镜像

Actions 使用仓库的 `GITHUB_TOKEN` 发布镜像。服务器单独使用可读取这两个镜像的 GitHub 账号，创建有 `read:packages` 权限的 **Personal access token (classic)**；组织启用 SSO 时为 token 授权。以 deploy 用户登录：

```bash
read -rsp 'GHCR read token: ' GHCR_TOKEN; echo
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
unset GHCR_TOKEN
```

token 留在服务器的 Docker 登录配置中，不放到仓库、业务环境文件或命令行参数。公开镜像可免登录。首次发布后检查 GitHub Packages 中两个包的访问权限；原本已存在且未关联当前仓库的包需要额外授权 Actions 访问。详见 [GHCR 权限与认证](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。

## 5. 配置 GitHub Actions

仓库 **Settings → Environments** 创建 `production`，添加以下 Secrets。建议限制此 Environment 仅允许 main；需要人工批准上线时再设置 required reviewers。

| Secret | 内容 |
| --- | --- |
| `DEPLOY_HOST` | 服务器公网 IPv4 或可解析主机名（当前脚本不接受 IPv6 字面量） |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_PORT` | SSH 端口；省略时为 22 |
| `DEPLOY_SSH_KEY` | 上一步部署私钥的完整内容，含 BEGIN/END 行 |
| `DEPLOY_KNOWN_HOSTS` | 经过核对的服务器 SSH 主机公钥记录 |

生成主机记录，例如在本机执行 `ssh-keyscan -p 22 -H SERVER > known_hosts`。用服务器控制台执行 `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`，与 `ssh-keygen -lf known_hosts` 中对应指纹核对后再保存 Secret。非 22 端口必须使用实际端口采集。工作流启用严格主机验证，不在运行时盲目信任扫描结果。

仓库需要允许 Actions 运行及创建 Packages；工作流已为 build job 声明 `packages: write`。若组织策略限制 Actions 或 Packages，需要管理员在组织层放行。

提交并推送这些文件至 **main** 后自动部署；也可以在 **Actions → Deploy production → Run workflow → main** 手动运行。部署目录固定为 `/opt/zhigenews`，不是仓库目录。默认每次 main 推送都会部署，包括文档变更；只想手动发布时删除工作流 `push` 配置。不要将部署凭据提供给不可信分支或 PR。

Actions 会：

1. 构建后端镜像；构建双前端时检查 API 契约、TypeScript 并运行 API 客户端测试。
2. 发布 `ghcr.io/<owner>/<repo>-backend` 和 `...-web`，标签为 commit SHA、run ID、attempt；实际部署固定为镜像 digest。
3. 上传不含密钥的 Compose、脚本和镜像引用到 `releases/<release-id>/`。
4. 拉取镜像、检查密钥格式和必填项，再停止 beat/API，等待 worker 退出。
5. 对已初始化数据库生成迁移前 SQL 备份，执行 Alembic；首次运行 `init`，以后保留管理员和已删除来源，不重复导入默认来源。
6. 迁移新闻索引，启动所有服务，等待 API、数据库、Redis、worker 和 Caddy 健康，并从服务器检查两个域名的 HTTPS 首页与 `/healthz`。
7. 全部通过后更新 `current` 和 `previous` 软链接。它们记录成功版本，不会自动控制容器回退。

并发发布由 Actions concurrency 和服务器 `flock` 双重串行化。密钥检查只验证格式/非空，不会调用付费模型服务。beat 检查仅覆盖进程运行；调度与真实生成要在业务验收中检查。

## 6. 首次部署验收

访问 `https://news.example.com` 和 `https://admin.example.com`，管理员用 `backend.env` 的账号密码登录。检查：

- 首页和深层路由刷新成功；管理员登录、退出及匿名用户会话正常。
- 两个域名的 `/healthz` 返回 `status: ok`；错误 API 路径应返回 API 错误而非前端 HTML。
- 配置偏好后生成一份真实简报，确认来源引用、worker 执行、公开进度和管理员 SSE 更新；确认计划任务由 beat 正常触发。

首次 `init` 会导入默认 RSS 来源，beat 启动后开始按计划采集。现有从 NewsNow 升级的数据库须先完成 README 中的旧来源清理，不能用初始化代替。

登录服务器后定义运维函数；它会按 `current` 指向的成功版本读取配置：

```bash
export DEPLOY_ROOT=/opt/zhigenews
dc() {
  local files=(-f "$DEPLOY_ROOT/current/compose.yaml")
  if [[ -f "$DEPLOY_ROOT/compose.override.yaml" ]]; then
    files+=(-f "$DEPLOY_ROOT/compose.override.yaml")
  fi
  docker compose -p zhigenews-prod \
    --env-file "$DEPLOY_ROOT/.env" \
    --env-file "$DEPLOY_ROOT/current/release.env" \
    "${files[@]}" "$@"
}
dc ps
dc logs --tail=100 api worker beat web
dc exec -T worker celery -A zhigenews.workers:celery_app inspect ping
```

`current` 仅在首次完整成功后存在。首次失败时，把函数中的 `current` 换为 Actions 日志里的 `releases/<release-id>`。不要把开发环境 `verify_runtime.py` 原样用于生产：它使用 HTTP 和本地 Origin，与生产 Secure Cookie 设置不同。

## 7. 更新、备份和回退

**更新代码：** 推送 main。**只改业务配置：** 编辑服务器 `backend.env` 后重新运行工作流；也可执行 `bash /opt/zhigenews/current/deploy.sh`，使用当前镜像重新执行部署。Compose 会更新受影响容器；模型密钥不进入前端镜像。

服务器持久数据：

| 位置 | 内容 |
| --- | --- |
| Docker 卷 `zhigenews-prod_mysql-data` | 业务数据库、会话、任务、checkpoint |
| Docker 卷 `zhigenews-prod_redis-data` | Celery 队列和 Redis 数据 |
| `/opt/zhigenews/data` | 新闻与运行工作区；容器与宿主机绝对路径一致，供沙箱绑定 |
| Docker 卷 `zhigenews-prod_caddy-data` / `caddy-config` | TLS 证书及 Caddy 状态 |
| `/opt/zhigenews/.env`、`backend.env`、`.initialized`、可选 `compose.override.yaml` | 基础配置、业务密钥、首次初始化标记、宿主代理覆盖配置 |
| `/opt/zhigenews/backups` | 每次更新前的数据库 SQL 备份 |
| `/opt/zhigenews/releases`、`current`、`previous` | 部署文件、镜像 digest、成功版本记录 |

日常停机使用 `dc stop`，不删除数据。自动 SQL 备份不含运行文件、密钥和 Redis，也不自动清理历史备份；应按容量制定保留策略并复制到服务器外。需要完整恢复点时，在 API、beat、worker 停止并完成排空后，同时备份数据库、`data/`、配置和初始化标记，并保存所使用镜像 digest。Redis 队列的恢复要与数据库一致，避免重放旧任务。

例如使用上述 `dc` 函数制作一个完整的应用文件/SQL 备份（部署期间不要并行执行）：

```bash
umask 077
backup="/opt/zhigenews/backups/manual-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup"
dc stop beat api
dc stop worker
set -o pipefail
dc exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -u root --single-transaction --routines --triggers --events --no-tablespaces --set-gtid-purged=OFF zhigenews' | gzip > "$backup/database.sql.gz"
# 文件由容器创建，完整打包可能需要 sudo；备份含密钥，保持目录权限 700。
sudo tar -C /opt/zhigenews -czf "$backup/app-files.tar.gz" data .env backend.env .initialized releases current previous
dc up -d --wait api worker beat web
```

Nginx 模式还需将 `compose.override.yaml` 加入 tar 参数，并另行备份宿主 Nginx 站点配置和证书。首次只有一个成功版本时没有 `previous`，从 tar 参数中删去它。任一步失败时先处理错误，再恢复服务；不要把不完整备份当成恢复点。

**部署失败：** Actions 会失败并显示服务状态，`current` 不前移；但容器可能已停止或部分更新，旧链接不代表旧服务仍正常。拉取或预检查失败发生在停机前，可修正配置后重试；迁移或启动失败先检查对应 release 的日志。

**回退应用：** 确认当前数据库结构兼容旧镜像后，执行旧 release 的脚本，例如 `bash /opt/zhigenews/previous/deploy.sh`。脚本仍会执行迁移检查；遇到旧代码不认识的新迁移 revision 会失败，不会自动降级数据库。首次升级失败时，旧成功版本仍在 `current`，可用它重试恢复。不要通过重跑旧 Actions run 代替选择已保存的 digest，因为重新构建可能带来不同的基础镜像。

**不兼容的数据库变更：** 需要停机，用对应备份恢复数据库和数据文件、保持原加密密钥，再运行匹配的旧 release。恢复会覆盖备份之后的数据，需按实际恢复点操作；这里不自动执行破坏性数据库恢复，也不承诺无损 downgrade。迁移失败可能已部分应用 DDL，不能仅看命令退出码判断数据库没有变化。

迁移已有生产数据时，先备份并恢复数据库、`data/` 和原安全密钥；确认已有管理员及初始化完成后创建 `/opt/zhigenews/.initialized`，避免首次部署再次导入已删除的默认来源。空数据库不要预先创建该标记。

## 8. 常见问题

| 现象 | 检查 |
| --- | --- |
| `unauthorized` / `denied` 拉镜像 | deploy 用户是否登录 GHCR、token 是否过期、包访问权限、SSO |
| SSH 验证失败 | 私钥格式、authorized_keys 权限、端口与 known_hosts 指纹；不关闭 StrictHostKeyChecking |
| HTTPS 检查失败 | A/AAAA、80/443、安全组、Caddy 日志、证书申请限制、服务器能否访问自己的公网域名 |
| 登录或写请求 403 | 使用 HTTPS；域名与配置一致，Origin 没有额外端口；改域名后重新部署 |
| worker 正常但生成失败 | 模型/Tavily 配置、外网访问、Docker socket、沙箱镜像；`data` 挂载必须保持同一绝对路径 |
| MySQL 不健康 | 密码是否匹配已存在的数据库；不能通过改环境变量重置已有数据库用户 |
| 网段冲突 | 同步调整 subnet、动态地址池、Caddy IP 和可信 `/32`；已有网络需在停机后重建，保留卷 |
| 已移除来源重新出现 | 检查是否误删 `.initialized` 或手动重复运行了 `init` |

配置语义参考：[GitHub 镜像发布](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)、[Compose 服务配置](https://docs.docker.com/reference/compose-file/services/)、[Caddy 反向代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)。
