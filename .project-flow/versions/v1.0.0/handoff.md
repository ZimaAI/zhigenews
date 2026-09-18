# v1.0.0 续接入口

当前：v1.0.0 / 未冻结 / DISCOVER。无应用源码、无候选基线、无后端交接，未开展正式前后端实现。

评审入口：`docs/releases/v1.0.0/draft/DISCOVERY.md`；技术依据：`docs/research/` 三份文档；真实验证：`evidence/discovery-validation.json`。

恢复命令：

```powershell
python .agents/skills/prototype-to-product/scripts/version_flow.py resume --root . --version v1.0.0
```

先核对 pending_stage_review。用户还未回答时恢复同一个“进入 ITERATE 或继续调整”的选择点；用户已明确选择且内容未变时，记录真实 answer-review，再推进 ITERATE，不重复确认。

进入 ITERATE 后实现 `docs/releases/v1.0.0/draft/prototype/` 的两个独立 Vue 原型、共享组件/固定 mock/状态重置；同步领域模型、唯一 OpenAPI 契约草稿和验收场景。正式源码计划 `backend/`、`apps/user-web/`、`apps/admin-web/` 尚未建立。

既定用户要求无需重问。bash/CAS 通道、偏好匹配、推送语义、模型/源配置等候选行为通过原型展示，尚无用户对具体基线的批准。不会把新闻源抽样或工作流 doctor 通过当成集成通过。
