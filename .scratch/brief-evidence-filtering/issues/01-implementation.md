# 逐条过滤无效证据并发布剩余简报

Type: task
Status: resolved
Blocked by: none

按 spec.md 修改 Harness 校验与结果组装，沿用现有执行/发布流程；补充回归与真实 MySQL 发布测试，完成后提交并推送。

## Answer

已将逐条证据缺陷改为过滤并记录原因；畸形 URL 和缺失/无效溯源信息不会中断其他新闻。过滤后使用保留首条新闻的标题和摘要作为标题与导语，全部剔除时生成明确的空结果。运行事件保留数量和逐条原因，limitations 驱动现有 partial 发布流程；不增加模型调用。

模拟模型驱动真实 Harness、隔离 MySQL、产物保存及站内发布：117 项通过，覆盖单条发布、全过滤空结果、发布重放幂等、正常空结果与基础设施错误继续传播。Ruff 与 git diff --check 通过。见 ../verification.md。
