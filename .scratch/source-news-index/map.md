# 来源新闻索引与 Agent 自主检索：探索记录

本文件保留核查事实与讨论过程。当前规格见 [spec.md](spec.md)，实施任务见 [01-implementation.md](issues/01-implementation.md)。用户调用 to-spec 后又确认 Q3–Q5 均采纳推荐，以下状态已同步。

状态：Q1–Q5 均已确认，实现与验证完成。日期：2026-09-19。结果见 [验证记录](verification.md) 与 [双轴审查](review.md)。

## 用户已确定的方向

- 每个新闻来源维护自己的最近 24 小时新闻索引；采集任务完成后维护索引并剔除超时条目。
- Agent 运行开始时不构建 Evidence 索引，不把新闻列表嵌入首条用户消息。
- 提示词说明新闻目录结构、索引及文件含义，并提供当前日期，指导 Agent 按用户偏好检索最近 24 小时的新闻。
- 索引选择、关键词搜索、文件及阅读范围由 Agent 在循环中自主决定。
- Agent 可访问新闻存储目录和本次运行工作目录；新闻目录只读，运行工作目录可读写，沙箱须执行相应限制。

## 设计树

1. 时间语义
   - Q1（已答）：按新闻发布时间判定，缺失则排除，不用采集时间替代。
   - Q2（已答）：按运行开始时固定 24 小时窗口；提示词给出明确起止时间与时区。
   - 后续：基于上述决定明确边界、过期维护及读取时的时效要求。
2. 采集与索引
   - Q4（已答）：每次实际采集尝试结束（含失败/304/未变化）维护；接受两次维护间暂留过期项，由运行窗口与最终校验把关。
   - Q5（已答）：累计已采集的 24 小时内新闻，去重保留到过期，不因退出上游最新列表而移除。
   - 后续：索引内容、已有数据迁移、运行期间索引版本的一致性。
3. Agent 检索与证据引用
   - 已查明：提示词内嵌完整 evidence_index，最终引用验证依赖预加载 evidence 字典；两者必须一起改。
   - 后续：历史正文的可见性与可引用性、检索结果与最终引用的衔接。
4. 访问权限
   - 已定：新闻只读，本次运行工作目录可读写。
   - Q3（已答）：文件工具和 bash 均可读写整个本次工作区；CAS 只约束 write_file，新闻目录始终只读。
   - 后续：禁用来源的可见性与历史正文访问范围。

## 实施前核实的实现事实

- `backend/src/zhigenews/execution.py:163`：取每个启用来源的最新快照全部条目，存入运行 evidence；无发布时间筛选。不是遍历所有历史快照。
- `backend/src/zhigenews/harness/runner.py:518`：首条用户消息嵌入 evidence_index，条目摘要最多 500 字；已带 fixedAt，但当前值源于任务创建时刻，不一定是实际开始时刻。
- `backend/src/zhigenews/harness/runner.py:140`：结果引用必须存在于预加载 evidence 字典。新流程需要按最终选中 ID 解析可信来源记录。
- `backend/src/zhigenews/harness/runner.py:158`：最终校验已有时间检查，但放行发布时间为空的新闻，并允许 fixedAt 后 5 分钟。
- `backend/src/zhigenews/ingestion/service.py:279`：按来源保存不可变 raw、parsed、manifest 文件，再原子替换 latest；现有历史文件未自动清理。
- `backend/src/zhigenews/ingestion/service.py:431`：304、内容不变及失败不发布新快照，因此索引维护不能仅挂在新快照发布后。
- `backend/src/zhigenews/workers.py:287`：单源文件锁和数据库租约提供现有串行采集边界。
- `backend/src/zhigenews/application.py:443`：修改来源 URL/类型会重置其快照状态，旧文件仍在；新索引需按来源当前配置区分。
- `backend/src/zhigenews/harness/files.py:58`：当前只允许写 /workspace/output；`sandbox.py:61`：bash 对 /rss 和 /workspace 均只读。
- `backend/src/zhigenews/harness/runner.py:378` 与 `execution.py:380`：子 Agent 与固定数据评估也依赖旧输入结构，需要同步适配；评估仍应保留固定资料和时钟。

## 本轮讨论记录

- 用户已选择 Q1「按发布时间；缺失则排除」与 Q2「固定为运行开始时的 24 小时窗口」。
- 用户调用 to-spec，已将讨论综合为规格与本地实现任务。
- 用户随后回复“Q3–Q5 均采纳推荐”，已更新规格、任务与本记录，无需再次确认这三项。
- 用户随后调用 implement，实施完成；最终完整测试 218 passed、1 skipped，双轴审查无硬性违规或需求缺陷。

## 项目背景

- 当前版本 v1.0.0，状态为 FRONTEND_VERIFY；本次讨论不修改版本或验收状态。
- 本次按用户指定的 grill-with-docs 技能开展设计访谈，联用 grilling 与 domain-modeling。
- 现有规格禁止将抓取/榜单时间冒充来源发布时间，见 `docs/releases/v1.0.0/draft/spec/03-domain.md`。
- 旧规格将 bash 的持久挂载设为只读，持久写入通过 CAS 文件服务；已确认的新要求允许 bash 写本次工作区，CAS 仅约束文件工具，实施时同步旧说明。
