# v1.0.0 的讨论决定

本文件区分用户明确要求、助手建议、真实批准。日期：2026-09-18。

| ID | 状态与来源 | 决定 | 影响 |
| --- | --- | --- | --- |
| DEC-001 | 用户明确要求；本轮需求原文 | Python/FastAPI/LangGraph/MySQL；双独立 Vue 3 前端 | REQ-PLT-001 |
| DEC-002 | 用户明确要求 | Gateway / Harness 分层，使用 LangChain create_agent；三类新闻、六工具、沙箱、CAS、记忆、消息修复、摘要和评估 | 需求清单全部相应 REQ |
| DEC-003 | 用户明确要求 | 联网研究开源方案、前端读取 design.md | 三份研究文件、REQ-UX-001 |
| DEC-004 | 助手建议；用户授权自选渠道 | 站内收件箱+可选 SMTP 邮件，提交与送达分离 | REQ-DELIVERY-001 |
| DEC-005 | 助手建议；待原型确认 | Linux 隔离 bash，只读业务挂载+临时 /tmp；持久文档走 CAS | REQ-FS-001/002/004 |
| DEC-006 | 助手建议；源码调研依据 | MySQL 社区 checkpointer/store 适配优先，后端实测；不引入 PostgreSQL | REQ-MEM-001 |
| DEC-007 | 助手建议；源码调研依据 | 自建索引式工具消息重排；继承摘要类但分离 summary state 和模型输入渲染 | REQ-MSG-001、REQ-SUM-001 |
| DEC-008 | 助手建议 | Celery/Redis+持久到期时间，HTTP 不承担长时 Agent 执行 | 架构与每日自动推送 |
| DEC-009 | 用户显式调用技能所产生的流程约束 | 本轮 DISCOVER；阶段结束展示实际成果后询问进入 ITERATE 或修改 | 当前无基线/后端/前端批准；未执行下一阶段 |

技术参数、页面和目录均为草稿。完整范围见 `docs/releases/v1.0.0/draft/spec/01-requirements.md`；未来用户反馈在此追加并指明替代关系，不篡改已发生的授权来源。
