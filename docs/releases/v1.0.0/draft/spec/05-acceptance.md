# 验收目录（ITERATE 草稿）

以下 AC ID 稳定保留，关联 `01-requirements.md` 中的 REQ。当前是**验收定义，全部尚未在本表登记运行**，不是通过报告。`frontend` 的原型验证可检查模拟交互；正式前端验收仍须连接真实后端重验。`backend/integration` 不能用示例事件或页面 toast 证明通过。实际结果和证据由阶段报告记录，后续删除需求保留 retired 行及理由。

| AC ID | 关联 REQ | phase | 可观察的通过条件 |
| --- | --- | --- | --- |
| AC-UI-001 | REQ-PLT-001, REQ-UX-001 | frontend | 用户/管理员为两个可独立启动与构建的 Vue 3 项目；共用契约与语义组件，分别遵循 design-user.md / design.md，用户主题不污染管理员；首页持续标明模拟数据，重置恢复固定时钟与 seed。 |
| AC-UI-002 | REQ-AUTH-001, REQ-UX-001 | frontend | 登录/注册有必填与格式校验、提交中、失败保留输入和退出；普通用户进入管理入口显示无权限；原型不宣称真实鉴权。 |
| AC-UI-003 | REQ-PREF-001 | frontend | 可通过主题封面/小卡添加移除主题；搜索和分类只筛候选，隐藏已选不取消订阅，搜索词不作为关键词保存；包含/排除关键词、prefer/required、来源/语言/窗口/条数/深度可编辑；显式保存后显示新版本，失败不丢草稿。 |
| AC-UI-004 | REQ-PREF-001, REQ-MEM-001 | frontend | 偏好未保存离开有明确处理；页面说明仅后续新运行生效；记忆显示来源/更新时间，可删除，失败保留数据。 |
| AC-UI-005 | REQ-BRIEF-001 | frontend | 今日页面展示摘要、推荐理由、来源入口与发布时间未知提示；按主题筛选；生成中保留旧简报；完成后可打开新一期。 |
| AC-UI-006 | REQ-BRIEF-001, REQ-UX-001 | frontend | 历史支持日期/主题/状态筛选及无结果/分页；详情展示内容版本和偏好快照；返回保留筛选。 |
| AC-UI-007 | REQ-DELIVERY-001 | frontend | 时间/时区、邮箱渠道、验证状态可操作；暂停后显示停止未来调度，恢复显示下一次日期；未验证邮箱不能伪装测试成功。 |
| AC-UI-008 | REQ-DELIVERY-001, REQ-BRIEF-001 | frontend | 简报已生成且邮件失败同时可见；重试增加原 briefId 的尝试，不重写简报；submitted 显示已提交而非已送达。 |
| AC-UI-009 | REQ-AGENT-002, REQ-OBS-001 | frontend | 运行时间线可见有界事件与子任务；点击取消先显示取消中，随后取消；连接状态与运行状态分开。 |
| AC-UI-010 | REQ-UX-001 | frontend | 两端正常/loading/empty/error/partial/unauthorized 可演示；320/375/768px 重排，长标题无全页横向溢出；键盘可达操作，弹窗可关闭并恢复焦点。 |
| AC-UI-011 | REQ-SRC-001, REQ-SRC-002 | frontend | 管理员可新增/编辑/启停源、模拟采集；NewsNow 展示不同上游/有效周期，RSS 失败保留最后成功值，显示下次抓取。 |
| AC-UI-012 | REQ-ADMIN-001 | frontend | 可配置模型 ID/端点/角色、输入替换 key、模拟连接测试与启停；输入 key 不在列表、提示或日志回显，失败保留非秘密字段。 |
| AC-UI-013 | REQ-ADMIN-002 | frontend | 参数与提示词草稿可保存/校验/发布；显示配置版本及新运行生效说明；已发布版本不可直接改写。 |
| AC-UI-014 | REQ-OBS-001 | frontend | 管理运行列表可过滤状态/模型/时间，详情包含工具参数和结果摘要、压缩、文件冲突及子任务示例；全部事件标明模拟且无私有思维链。 |
| AC-UI-015 | REQ-EVAL-001 | frontend | 固定用例可编辑/保存，选择配置发起模拟实验，可比较两次结果；相关性/忠实度与引用规则分开标明，排队或失败无伪造分数。 |
| AC-UI-016 | REQ-AUTH-001, REQ-DELIVERY-001 | frontend | 管理员可切换用户状态并查看投递故障；重试使用同一期简报，目的地脱敏；无运行样本不显示虚构完成率。 |
| AC-BE-001 | REQ-PLT-001, REQ-AGENT-001 | backend | FastAPI Gateway 与 Harness 分层；模型/工具循环实际来自 LangChain create_agent + LangGraph，数据库为 MySQL；正式进程可按说明启动。 |
| AC-BE-002 | REQ-AUTH-001 | backend | 未登录 401、普通用户管理操作 403、跨账号资源不可见；伪造 userId/threadId 不能访问他人文件、记忆、简报或运行。 |
| AC-BE-003 | REQ-PREF-001, REQ-BRIEF-001 | backend | 偏好并发版本冲突返回 409；排除词优先、required 命中规则可重复验证；无匹配不放宽或凑条数，未知发布时间不冒充新新闻。 |
| AC-BE-004 | REQ-SRC-001 | backend | 至少两个 NewsNow 源按各自上游周期调度；本地不快于上游；重复调度不并发拉取同源；缓存年龄及失败可追溯。 |
| AC-BE-005 | REQ-SRC-002 | backend | RSS 条件请求/304、超时、坏 XML 与退避有可重复样例；原始文件与元数据按源/日期/快照落盘；失败不覆写有效快照。 |
| AC-BE-006 | REQ-SRC-003, REQ-TOOL-001, REQ-FS-003 | backend | 六个必需工具可实际调用；Tavily 保留来源与查询并限制结果/调用/超时；list/search/bash 输出有上限与截断标志，read 支持行范围。 |
| AC-BE-007 | REQ-FS-001 | backend | 合法虚拟挂载可读取；`../`、宿主绝对路径、盘符/UNC、符号链接/重解析点及路径替换后越界均拒绝；RSS 只读且其他用户根不可见。 |
| AC-BE-008 | REQ-FS-002 | backend | 读片段仍记录全文件 hash；并发变更后写返回 FILE_CHANGED；重读后可写；两个并发覆盖仅一个成功；新建排他且合法父目录必需。 |
| AC-BE-009 | REQ-FS-004 | backend | bash 在隔离环境运行，无宿主凭据/他人目录/网络；持久挂载写入失败，CAS write_file 合法写入成功；无隔离环境时不能回退宿主 shell。 |
| AC-BE-010 | REQ-AGENT-002, REQ-MEM-001 | backend | Agent 能按工具结果继续选择行动且受总预算限制；MySQL checkpoint 经进程重启可恢复；子任务共享预算/取消并隔离 thread；长期记忆按用户持久化。 |
| AC-BE-011 | REQ-MSG-001 | backend | 多工具错序、缺失、孤儿、重复及中断日志经过修复后每个 tool_call 配对；user/AI 相对顺序保持，原始 seq 不改；重复修复幂等且不重做副作用。 |
| AC-BE-012 | REQ-SUM-001 | backend | 中间件继承 SummarizationMiddleware，消息/token/比例均可触发；摘要包含旧摘要，独立字段保存；最新用户原文保留，另一个渲染器注入摘要；总预算计入摘要/工具/schema/输出预留。 |
| AC-BE-013 | REQ-ADMIN-001, REQ-ADMIN-002 | backend | 密钥加密保存、只写不回显，可替换/撤销；模型能力实际测试；配置发布不可变且运行绑定快照，热修改不能改变正在运行的参数。 |
| AC-BE-014 | REQ-OBS-001 | backend | 运行事件持久化并脱敏，记录真实延迟、用量与预算；未知指标保持未知；SSE 断线用 Last-Event-ID 无重复遗漏地追赶，不改变运行终态。 |
| AC-BE-015 | REQ-EVAL-001 | backend | 实验绑定固定来源/偏好/时钟和配置/评分器版本；规则检查、人工与 LLM 评分可区分；评分器失败为不可用而非 0/通过；实验不发送邮件。 |
| AC-INT-001 | REQ-BRIEF-001, REQ-DELIVERY-001 | integration | 真实偏好 → 采集快照/搜索 → Agent → 可追溯简报 → 站内/邮件提交闭环；部分来源失败可产生明确 partial，证据不足不会发布虚构内容。 |
| AC-INT-002 | REQ-DELIVERY-001 | integration | 时区/DST/暂停恢复与每日唯一键经过验证；队列重投不产生重复简报；同幂等键返回原运行，重试推送引用原内容版本；未知投递不冒充已送达。 |
| AC-INT-003 | REQ-PLT-001, REQ-UX-001, REQ-AUTH-001 | integration | 两个正式前端接同一真实 Gateway；交换请求/响应通过权威 schema，真实角色、保存失败、取消、SSE 与投递错误可操作；不依赖 mock 即可完成核心流程。 |

原型浏览器检查优先覆盖 AC-UI-003/005/008/011/012/013/015 的完整操作路径，以及 AC-UI-010 的布局与键盘；其余状态逐项记录。后端正式实施和验收时将 AC-BE/INT 拆成可运行检查并附环境、输入、预期、实际和证据路径，不能继承原型阶段的通过状态。
