# 修复来源新闻索引升级后空目录

Type: task
Status: resolved
Blocked by: none

## 问题

bbbc69a 将新闻存储从 `<kind>/<source>` 改为 `<kind>/<source>/configs/<identity>`，未迁移旧快照；新运行只授权新目录。实际运行三个来源均缺失，旧记录仍在卷中。

## 验证

`uv run --project backend pytest backend/tests/test_news_upgrade.py -q`：2 failed。旧目录的 `/news` 发现结果为空，升级后首次 HTTP 503 返回 snapshot=None。

## 修复范围

在 worker 消费任务前执行幂等的本地新闻迁移；采集入口也适配旧快照。按来源配置隔离，保留 evidence_id 与旧文件，迁移建立最近 24 小时索引，不依赖外网或简报运行临时重建。验证当前运行卷的发现、读取与证据解析。

## Comments

- 候选原因：缺少数据迁移；来源配置身份不一致；沙箱挂载/权限。实际采集与运行路径一致，旧目录存在、新目录缺失，确认升级迁移遗漏。

## Answer

- 新增 `ingestion/upgrade.py`，将匹配来源 ID、类型、规范化 URL 的旧快照复制到配置目录，保留旧文件和 evidence_id，建立最近 24 小时索引。保留已有较新快照及索引，支持中断重试与幂等执行。
- 新增 `migrate-news` 运维入口；Compose worker 消费任务前在来源锁内自动迁移。采集入口同样适配，HTTP 503/304 时仍能使用已有证据。简报入口继续只读索引。
- 修复前的两个复现用例均变绿；新增迁移覆盖共 7 项全部通过。
- 全后端检查：225 passed、1 failed、1 skipped。唯一失败为新增端到端升级夹具缺少 interval 字段；补齐夹具后新/旧布局端到端用例复验 2 passed，覆盖真实 MySQL、Harness 读取和引用输出。其余通过项包含 Docker/Linux 集成。跳过项是未配置隔离数据库的迁移测试。本次没有数据库结构变更。
- Ruff 与 diff 检查通过。
- 已构建镜像并更新本地 worker/beat；迁移现有运行卷。真实检查：Hacker News 42、中国新闻网 251、Solidot 3，共 296 条索引新闻均可解析证据；文件工具及真实 Docker 沙箱均能读取三个索引。检查只读取真实新闻，临时验证工作区已清理；没有重新发布用户简报。
