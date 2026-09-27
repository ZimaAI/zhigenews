# 简报逐条证据过滤验证

日期：2026-09-27。

## 回归

修复前运行 `uv run --project backend pytest backend/tests/test_evidence_filtering.py -q --tb=short`：10 failed、3 passed。复现未知引用/无效 URL/缺少溯源字段导致 HarnessError、畸形 IPv6 URL 导致 ValueError、过滤后仍保留旧标题导语。

修复后最终检查：

```text
uv run --project backend python .scratch/reader-brief-experience/run_tests.py backend/tests/test_evidence_filtering.py backend/tests/test_harness_runtime.py backend/tests/test_thinking_models.py backend/tests/test_execution.py backend/tests/test_workers.py -q --tb=short
117 passed, 3 warnings in 34.55s
```

使用既有隔离数据库测试脚本，真实 MySQL 和 create_agent，模型为明确的模拟输入，无真实外部模型请求。测试结束删除该次随机测试数据库与临时目录。警告为测试启动导入顺序和 Starlette/AnyIO 弃用提示。

覆盖：无效证据逐条过滤、URL 解析异常、无效采集时间、时间窗与去重、有效记录仍可从来源解析、存储错误继续传播；无过滤时保留原文案；过滤后 JSON/Markdown/完成记录/数据库/发布内容一致；只剩一条仍 partial 发布；全部剔除正常结束且无空简报；运行和发布重放不重复生成/发布。

修改的 Python 文件 Ruff 检查通过，`git diff --check` 通过。没有数据库结构或前端协议变更。
