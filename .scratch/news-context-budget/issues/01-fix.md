# 修复读取新闻后上下文超限

Type: task
Status: resolved
Blocked by: none

## 复现

最新失败运行 `gen_4bbcdbac361e41a68bbcc75f3a1101e7`：窗口 32768、输出预留 8192。三次并行索引读取后摘要仅从 18677 tokens 降至 18281；继续读取文件后 CONTEXT_BUDGET。

`uv run --project backend pytest backend/tests/test_harness_runtime.py -k large_recent -q`：1 failed，真实 Harness/FileService 路径复现相同错误。

## 修复范围

摘要保留消息数不能作为硬下限；超出 token 目标时继续纳入完整的 AI/工具结果组，保留最新用户原文、消息协议和日志。保留实际请求的容量检查。

## Comments

- 排查候选：固定保留 8 条消息阻止压缩近期大结果；固定开销估算不足；摘要失败。最小复现与真实日志支持第一项。

## 修复与验证

- 摘要计划继续以最近消息数为优先保留范围；若保留内容加固定开销超出 token/窗口比例目标，则扩大摘要范围至完整的 AI/工具结果组。最新用户消息始终原样保留，Runtime 的最终完整请求容量检查不变。
- 新增三个用例：真实 Harness + FileService 的并行大索引读取与后续分页、摘要后的合法证据引用/原始日志/用户原文/消息配对；token 压力下保留可容纳的近期小结果；超长用户原文继续明确报错而非截断。
- Harness 和 thinking-model 相关测试 51 passed、1 skipped（该次未开启 Docker）；Ruff 通过。
- 只读加载报告中失败运行的真实 MySQL 检查点，在临时工作区用模拟摘要/主模型重放真实 Harness。原始历史 25492 tokens，经模拟简短摘要为 556，成功通过请求容量检查和结构化输出；最新用户原文保留。这里只验证流程，模拟摘要长度不代表真实供应商的压缩效果。未修改原运行、数据库或发布简报，临时工作区已清理。
- 完整后端测试（启用真实 MySQL/Docker）229 passed、1 skipped，141.99 秒；跳过项为未配置隔离数据库的迁移测试。Ruff 与 diff 检查通过。
- 已构建后端镜像，更新本地 worker/beat；容器内核对新摘要计划代码已加载。
