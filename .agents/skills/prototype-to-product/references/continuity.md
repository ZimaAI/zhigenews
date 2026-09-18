# 状态与连续性

项目只有一种受支持的格式：受管 JSON 的 schema_version=4，执行状态与计划的 workflow_version=4。不同产品版本共用此格式。
不识别或转换其他格式。检测到不受支持的状态或占用的受管目录时停止，不删除、覆盖、重标格式号或推断完成度。

注册表确定版本身份；版本 state 确定阶段、基线与授权；tasks 确定任务进度；冻结快照是设计主源。
后端 hNNN 是实施交接；checkpoint 是某次会话的续接记录；INDEX/RESUME 是可重建导航，不是另一份规范。
跨会话的完整协议见 [sessions.md](sessions.md)，阶段授权见 [stage-controls.md](stage-controls.md)。

每条 baseline/backend/frontend 授权绑定精确引用、manifest_sha256、真实用户原话、来源与时间；frontend 额外绑定后端 hNNN 及指纹。
会话变化本身不撤销已有授权，也不新增授权；当前用户暂停/范围限制优先，生产操作需独立授权。

默认同一工作区单个写入者。CLI 有本地排他锁，JSON 使用原子写入；整个多文件动作不是数据库事务。
进程中断可能留下未注册快照/交接/检查点，doctor 仅检测，不自动删除或修复。
只更新有变化的状态；阶段切换、有意义的工作结束与交接前保存 checkpoint。未取得证据的任务不得记为完成。

pending_stage_review 是阶段选择主源，不改变真实 stage。确认点 qNNNN 绑定当前成果，历史回答写入 history；是否推进由真实用户选择和验收条件共同决定，详见 stage-controls。
