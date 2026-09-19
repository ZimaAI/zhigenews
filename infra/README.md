# 本地基础服务

开发编排位于根目录 `compose.yaml`，Docker project 为 `zhigenews`。MySQL 8.4映射本机13316端口，Redis映射56386；`app` profile启动API（18000）、Celery worker和beat。

后端安装、迁移和验证步骤见根README及`.project-flow/versions/v1.0.0/handoff-input/runbook.md`。依赖通过`backend/uv.lock`锁定，API构建由`backend/Dockerfile`定义。迁移代码位于`backend/migrations`。

`zhigenews_runtime`命名卷在API和worker内挂载为`/var/lib/docker/volumes/zhigenews_runtime/_data`，与Docker daemon的卷路径保持一致。可信worker使用Docker CLI/socket创建短时隔离容器；沙箱仅只读挂载当前运行的workspace/rss，不挂载socket，且无网络、非root、资源受限。

数据库、Redis及运行数据使用持久卷。`docker compose stop`停止本项目并保留数据。原生Python调试使用根`data/`，容器使用命名卷；同一Agent运行不得混用两种路径。

此目录与`backend/`、`compose.yaml`共同纳入后端源码指纹。共享编排发生改变后，后端运行证据需重新核对。当前没有生产部署产物。
