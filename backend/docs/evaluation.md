# 固定输入评估接线

`zhigenews.evaluation` 不依赖 FastAPI、数据库、网络或发布服务。Gateway 接收空对象 `{}` 创建实验，在事务中复制当前用例修订、每个用例的 `preferenceSnapshot/fixedAt/sourceSnapshotIds`、来源证据、代码常量 Agent 配置及文件中的模型设置；使用 `freeze_dataset(cases, sources).version` 存储 `datasetVersion`，用 outbox 交给 worker。不存在的快照和空用例集直接拒绝，显式空快照列表是有效的无证据测试。`configVersion`由 Agent 常量内容确定；结果中的`modelId`为实际供应商模型 ID。可选裁判使用`EVALUATION_OPENAI_*`配置，不再从管理员维护的模型记录选择。

内部记录格式（不对前端返回 snapshot）：

```python
evaluation = {
    "id": evaluation_id,
    "name": name,
    "configVersion": config_snapshot["version"],
    "createdAt": created_at,
    "datasetVersion": freeze_dataset(cases, sources).version,
    "scorerVersion": "rules-v1+judge-model-config-revision",
    "snapshot": {"cases": cases, "sources": sources},
}
result = evaluate_record(
    evaluation, config_snapshot,
    generate=generate_fixed_case,
    judge=judge_fixed_case,  # 未配置时传 None
)
```

`sources` 是 `{snapshot_id: [evidence_item, ...]}`，每条证据至少有 `url/source/title/publishedAt`；`publishedAt` 未知为 null。`generate_fixed_case(case)` 接收复制的完整用例，包含 `evidence/fixedAt/preferenceSnapshot`，返回 `{items: [...], cost: number | None}`。worker 为每个用例组装独立 Harness，输入只挂载这些固定来源，关闭 `web_search` 和任何实时来源刷新，以 `fixedAt` 判断时效；不得调用正式简报发布入口。

`judge_fixed_case(case, items)` 返回 `{relevance: 0..5, faithfulness: 0..5, cost: number | None}`。调用真实评估模型，并将完整偏好、固定证据、生成结果送入明确的评分提示；固定评分提示/模型修订需纳入 `scorerVersion`。未配置或调用失败会保留 null 和简短错误，不伪造0分。人工评分必须单独以 `method=human` 保存，不能写成LLM已评分。

规则分别计算24小时内且时间已知的条目比例、去重比例、证据来源覆盖率、引用存在比例。来源覆盖是描述值而非要求每个来源都出现。引用存在不等于语义忠实；忠实度来自明确标注的LLM/人工评分。空输出无分母，引用准确率为null。

返回值符合正式 `Evaluation` DTO，包含逐用例和逐指标结果。成本合计只在所有生成及已配置评分调用的成本都已知时返回数值；未知任何一项则为null。延迟由真实单调时钟测量。回调失败为失败用例，错误内容不回显到公开DTO。worker只持久化评估结果，不创建真实用户简报或投递。

测试：工作区根目录设置 `PYTHONPATH=backend/src`，执行 `python -m unittest discover -s backend/tests -p test_evaluation.py -v`。测试输入均为 synthetic，不作为真实模型评分或完整AC-BE-015通过证据。
