# 新闻采集与搜索接入调研

调研日期：2026-09-18。阶段：DISCOVER。本文件提供可追溯的外部契约和设计建议，不表示适配器、调度器或生产连通性已经实现。已先阅读项目资料 `docs/reference/RSS.md`；其中地址作为候选清单，不能继承其“目前可用”的判断。

本文件的目录和限额示例用于解释采集机制；本轮合并后的目录命名、默认参数以 [v1.0.0 架构草案](../releases/v1.0.0/draft/spec/04-architecture.md) 和 [评审入口](../releases/v1.0.0/draft/DISCOVERY.md) 为准。研究示例不是另一份实现契约。

## 1. 结论与边界

本系统采用三条独立数据路径：NewsNow 按源轮询并缓存；RSS 按源轮询、保存原始响应及解析结果；Tavily 由 Agent 在一次运行的预算内按需搜索。Gateway 负责配置、查询和触发任务，采集由后台 worker 执行，Harness 读取已落盘的材料并调用搜索工具。

NewsNow 的 `interval` 与缓存 `TTL` 是不同概念。必须保存每源间隔，不能把全部热榜设为 30 分钟。RSS 的间隔则来自管理员配置、源的缓存提示和实际更新行为，不能伪称所有 Feed 都声明了固定刷新频率。

Agent 获得两个文件空间：只读 `/rss` 和该次推送专用的可写 `/workspace`。NewsNow 的候选条目由系统写入该次工作目录的 `input/newsnow.jsonl`，Tavily 的证据写入 `evidence/search/`，因此不需要为 Agent 开放服务器的 NewsNow 缓存、密钥或其他用户工作目录。

## 2. NewsNow：已核对的源码契约

原仓库 `ourongxing/newsnow` 现重定向至 `newsnext/newsnow`。本次固定检查提交 **`0f95b2c998dffbfd2ddbc51b47b5809887dc6b97`**，后续集成应记录部署实例对应版本，避免把 `main` 的变动当成稳定 API。仓库提供自部署方式及 MIT 代码许可证；这不证明公共部署具有商业 API 的可用性承诺。[官方仓库](https://github.com/newsnext/newsnow)

### 2.1 HTTP 接口、授权与错误

| 项目 | 源码可确认的行为 |
| --- | --- |
| 单源获取 | `GET {base_url}/api/s?id={source_id}`；`latest=true` 请求最新数据 |
| 成功响应 | `status` 为 `success` 或 `cache`，另有 `id`、`updatedTime`、`items`；可有 `info` |
| 条目 | `id`、`title`、`url`；`pubDate`、`mobileUrl`、`extra` 可选 |
| 截断 | 新抓取数据最多返回前 30 项，因此此接口是榜单快照，不是全量新闻流 |
| 异常 | 无效 source id 或无缓存且抓取失败会被转换为 HTTP 500；抓取失败但存在旧缓存时会回退旧数据 |

上述依据为 [单源 handler](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/server/api/s/index.ts) 和 [响应类型](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/shared/types.ts)。客户端需按响应结构校验，不把 `success` 直接解释为本次抓取到了新内容。

`POST /api/s/entire` 接收 `{"sources":["hackernews","solidot"]}`，读取多个源**已有缓存**，并不逐源执行抓取。数据库缓存未启用、没有匹配缓存或输入异常时，不能假设必定返回与请求等长的数组。[批量缓存 handler](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/server/api/s/entire.post.ts)

`/api/s` 支持匿名读取。配置了登录时，`Authorization: Bearer ...` 可以建立用户身份；匿名 `latest` 请求不能在 TTL 内强制刷新。未配置登录时的行为不同。生产集成建议自托管 NewsNow 并锁定版本，明确缓存与登录设置；使用公共实例则只按其允许的匿名能力运行，不自动生成登录令牌或依赖强制刷新。[授权中间件](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/server/middleware/auth.ts)

### 2.2 每源间隔如何取得

优先导入固定版本的 `shared/sources.json`，其中源 ID 已展开，`interval` 已具体化，单位是**毫秒**。这是源码元数据，不是本次确认的远端 catalog API。`shared/sources.ts` 直接加载该 JSON。[sources.json](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/shared/sources.json)、[加载代码](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/shared/sources.ts)

本次元数据中的实例：

| source_id | interval 毫秒 | 本系统导入秒数 |
| --- | ---: | ---: |
| `weibo` | 120000 | 120 |
| `aihot` | 300000 | 300 |
| `wallstreetcn-quick` | 300000 | 300 |
| `hackernews` | 600000 | 600 |
| `github-trending-today` | 600000 | 600 |
| `thepaper` | 1800000 | 1800 |
| `solidot` | 3600000 | 3600 |

若从 `pre-sources.ts` 重新生成，子源覆盖父源配置，父源未设间隔才使用默认值。父 ID 可能只是第一子源的 `redirect`；需要归一到实际 ID，避免重复轮询。`disable=true` 以及与 `CF_PAGES` 有关的 `disable="cf"` 会影响生成结果，因此本地 catalog 不保证与每个公共部署的可用源完全相同。[定义与生成逻辑](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/shared/pre-sources.ts)

默认 `interval` 为 10 分钟，独立 `TTL` 为 30 分钟。[缓存常量](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/shared/consts.ts) 需要特别注意：处于源间隔内时，handler 可以返回缓存、`status="success"`，并把 `updatedTime` 设为当前时间；`latest` 也不能绕过该源间隔。因此本系统应分别存 `fetched_at`、`upstream_updated_time`、`content_hash` 和条目的 `published_at`。`updatedTime` 不得填充为新闻发布时间，也不能单独证明内容变新。

### 2.3 本系统建议

- 在管理员源管理中保留 `upstream_interval_seconds`、`configured_interval_seconds`、`effective_interval_seconds`、`catalog_revision`；默认按导入间隔调度。管理员允许放慢，不应无理由短于源间隔。
- `base_url` 可配置，推荐自托管部署；公共实例可作为开发期接入点。catalog 升级先展示新增、删除、间隔变化，再更新已启用源，避免静默改变采集计划。
- 保存榜单原始 JSON 和按 URL/源内 ID 归一的新闻条目。正文缺失是正常情况，Agent 必须通过 RSS 或搜索补证据，不能根据一个热榜标题编造细节。
- 按内容哈希识别重复快照，保存抓取尝试时间但不把重复内容误认为新闻更新。回退缓存仍可提供候选材料，同时在运行输入中附带已知的时间与缓存状态。

## 3. RSS：官方协议、现有候选与抽样结果

RSS 2.0 的 channel 可选 `ttl`，单位为分钟；`skipHours`、`skipDays` 也是可选提示。缺少这些字段很常见，不能从缺失值推出统一间隔。item 的 `guid`、`pubDate` 可选，`guid` 也不一定是网页 URL。[RSS 2.0 规范](https://www.rssboard.org/rss-specification)

HTTP 条件请求应保存并回送 `ETag` / `Last-Modified`；304 表示内容未修改，不产生新正文。feedparser 官方说明了对应参数与 304 行为。[feedparser 条件请求](https://feedparser.readthedocs.io/en/latest/http-etag/) feedparser 能容忍部分非规范 Feed，`bozo` 标识及异常信息应进入采集记录；不能仅因 `bozo=1` 就声称一条新闻都无法解析。[feedparser 格式检测](https://feedparser.readthedocs.io/en/latest/bozo/)

官方目录确认了中新网的多个频道以及 36氪综合、文章、快讯等地址。[中新网 RSS 中心](https://www.chinanews.com/rss/)、[36氪 RSS 中心](https://www.36kr.com/rss-center) `docs/reference/RSS.md` 中的人民网、新华网、门户旧源、RSSHub 候选，尚未逐项验证，不默认全部启用。

本次在当前开发环境执行少量匿名 GET 的结果如下。这是一次网络抽样，不代表持续可用性或部署环境验收；未把新闻正文复制到本仓库。

| 检查地址 | 本次观察 | 接入判断 |
| --- | --- | --- |
| [NewsNow Hacker News](https://newsnow.busiyi.world/api/s?id=hackernews) | HTTP 200，JSON，`status=cache` | 契约抽样可用；实际新鲜度仍需采集运行观察 |
| [中新网即时 RSS](https://www.chinanews.com.cn/rss/scroll-news.xml) | HTTP 200，`text/xml`，正文以 RSS 2.0 XML 开始；有 ETag 和 Last-Modified | 可进入首批集成验证 |
| [IT之家 RSS](https://www.ithome.com/rss/) | HTTP 200，XML，约 205 KB；有 Last-Modified | 可进入首批集成验证；不能整份塞入一次工具响应 |
| [36氪快讯](https://36kr.com/feed-newsflash) | HTTP 200，但为 `text/html`，正文以 HTML 开始 | 官方地址存在，当前请求未拿到 RSS；应标为待验证/解析失败，不能以 200 判健康 |

建议首批先集成少量与 AI/科技相关且探测通过的 Feed，再逐步启用候选。来源有效性的判断必须包含最终 URL、状态码、响应体格式、解析结果和条目时间；仅目录可访问或 XML MIME 类型不足以证明内容持续更新。

### 3.1 轮询规则（本系统设计建议）

RSS 源保存基础间隔；快讯候选初始 10 分钟，科技资讯 30 分钟，低频博客 60 分钟。这些是可调的产品默认值，**不是各媒体公布的 SLA**。若 Feed `ttl` 或服务端明确缓存提示要求更长间隔，向后推迟下次请求；管理员可配置更慢轮询。采用少量正向随机抖动分散请求，不提前突破每源间隔。

HTTP 200 且内容哈希不变：更新抓取记录及条件请求元数据，沿用旧快照。304：更新检查时间，保留原内容。超时、429、暂时性 5xx：有上限的退避；收到 `Retry-After` 时遵循它。解析失败不覆盖最后成功版本。连续失败、长时间无新条目应分别展示，因为“接口不可用”与“媒体没有更新”不是同一状态。

### 3.2 本地目录与一致性（本系统设计建议）

```text
data/
  rss/{source_id}/
    raw/{YYYY}/{MM}/{DD}/{snapshot_id}.xml
    parsed/{YYYY}/{MM}/{DD}/{snapshot_id}.jsonl
    manifests/{snapshot_id}.json
    latest.json
  newsnow/{source_id}/{YYYY}/{MM}/{DD}/{snapshot_id}.json
  users/{user_id}/runs/{run_id}/
    input/preferences.json
    input/sources-manifest.json
    input/newsnow.jsonl
    evidence/search/{tool_call_id}.json
    output/briefing.md
    output/briefing.json
```

`raw` 保存收到的原始 Feed 字节，manifest 保存原 URL、最终 URL、响应时间、HTTP 条件头、内容 SHA-256、长度、解析状态；`parsed` 保存归一条目，便于按行读取和关键词搜索。正文和摘要保持来源标识与链接。路径中的 ID 由系统生成，不把远端标题、URL 或 Agent 输入直接拼入物理路径。

采集先在同一文件系统写临时文件，校验后原子发布不可变 snapshot，再更新 `latest.json`。一个 Agent run 固定 `sources-manifest.json` 的 snapshot ID：采集继续进行时，当前 Agent 读到的输入仍保持一致。`/rss` 只暴露该 run 允许访问的源和快照，并保持只读；`/workspace` 映射到唯一 `user_id/run_id`。输出通过用户要求的读取哈希与写入比较机制提交；采集 worker 不与 Agent 共用可写 RSS 挂载。

保存期限是管理员策略；被推送记录、评估集或正在执行的 run 引用的快照，在对应引用有效期内保留。首版可定期清理未引用且超过保存期的旧快照，无需引入额外对象存储。

## 4. Tavily：已核对能力与 Agent 工具约束

官方 Search 使用 `POST https://api.tavily.com/search` 和 Bearer API key。支持 `query`、`topic`、`search_depth`、时间范围、域名过滤及 `max_results`（0–20）。结果含标题、URL、片段、相关性分数；可请求 `usage` 和发表日期。新闻日期可能是估算的发布时间或更新时间，不应视为经出版方确认的时间。[Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)

官方文档当前将 basic search 计为 1 credit、advanced 为 2 credits；开发与生产 key 的默认速率分别为 100 和 1000 RPM。限流返回 429，若响应带 `Retry-After`，使用实际返回值。[计费说明](https://docs.tavily.com/documentation/api-credits)、[速率与重试说明](https://docs.tavily.com/documentation/rate-limits) 这些数值作为当前能力记录，程序使用可配置预算，不能写死为永久配额。

建议 `web_search` 的系统默认参数：

```json
{
  "topic": "news",
  "search_depth": "basic",
  "time_range": "day",
  "max_results": 5,
  "include_answer": false,
  "include_raw_content": false,
  "include_usage": true,
  "auto_parameters": false
}
```

这是本系统的初始策略：由 Agent 根据主题选择 `news` 或 `general`，允许在管理员限制内扩大时间窗口；模型厂商博客、技术发布可能需要 general。工具返回每项标题、URL、日期、有限片段及请求 ID，默认每项片段最多 1200 字符、最多 5 项，并再应用工具总输出限额。完整响应仅由后端存为本次工作目录中的证据文件。引用使用结果 URL，不引用 Tavily 自动生成的答案来替代新闻出处。

搜索额度按每次 run 的 `max_search_calls` 和 `max_search_credits` 限制，工具自行执行硬限制；Agent prompt 只作引导。API key 由管理员配置并仅在服务端解密使用，不进入 prompt、浏览器响应、文件挂载或追踪记录。搜索查询只携带必要的主题和关键词，不发送用户身份或完整个人偏好文档。

错误处理按 HTTP 类型区分：400/422 返回参数错误供 Agent 调整；401 报凭据配置错误；429 等待退避；432/433 为额度/计费限制，应停止本轮搜索扩张；5xx 或网络问题做有上限重试。错误是结构化工具结果，需保留 `tool_call_id` 对应关系，不能从消息列表删除失败的工具调用。[Search 错误响应](https://docs.tavily.com/documentation/api-reference/endpoint/search)

本次仅核对官方文档，未调用需 API key 的 Tavily 接口，也未产生付费请求。实际账号权限、地区连通性、SDK 版本和返回字段需在后续集成阶段验证。

## 5. 调度、缓存与运行观测建议

先采用共享 MySQL 中的持久化源调度状态和独立采集 worker。HTTP 请求不承担轮询任务，Gateway 重启不会重置采集时间。具体队列技术可在系统方案阶段统一选择；本能力不要求为了定时拉取单独引入另一套数据库。

| 数据记录 | 必要内容 |
| --- | --- |
| `news_sources` | 类型、源 ID/URL、启用状态、间隔来源与值、catalog 版本、`next_fetch_at`、最近成功时间、条件请求头、失败次数 |
| `ingestion_attempts` | 源 ID、开始/结束、HTTP 状态、错误类型、耗时、字节数、解析条目数、快照引用、是否内容改变 |
| `source_snapshots` | 内容哈希、原始文件路径、解析文件路径、抓取时间、上游时间、条目数 |
| `news_items` | 源内 ID、规范 URL、标题、可空发表时间、首次发现时间、证据快照、去重标识 |
| run 输入 manifest | 偏好版本、采集快照列表、查询窗口、搜索调用与证据引用 |

worker 按 `next_fetch_at` 领取到期记录，用数据库租约/原子领取避免两个进程同时抓同一源。租约只保护短期执行权，网络失败后按退避重新排程；数据库保存下一次时间而不是为每个 RSS URL 单独常驻一个进程。

去重优先保留来源：源内用 `source_id + external_id`，跨源用规范 URL，再辅以标题相似判断。相同事件的多个报道可形成证据组；不能只因标题相似就删除不同观点或更新版本。`published_at` 缺失时保留 null，用 `first_seen_at` 标记首次发现，禁止冒充真实发布日期。

管理员侧至少展示每源下次抓取时间、最近成功检查、最近内容变化、失败类型、耗时及条目数；Agent 追踪记录实际用了哪个快照、搜索次数/credits、引用覆盖和最终推送 ID。评估“新闻是否新鲜”时参考条目时间与证据质量，不使用采集成功率代替内容质量。

## 6. 待集成验证与验收输入

1. NewsNow：选定自托管或公共实例，确认固定 catalog 的源 ID 实际可用；验证间隔前后请求、匿名 `latest`、缓存回退、空结果、源禁用和毫秒到秒转换。
2. RSS：对待启用 Feed 验证真实 XML、编码、解析与条目时间；覆盖 200 内容变化、200 内容不变、304、HTML 200、超时和异常 XML。36氪本次 HTML 响应需在部署环境重新核查。
3. 本地存储：验证抓取中断不破坏已发布快照、Agent 运行固定快照、原始 XML 与解析结果可追溯、RSS 挂载只读、跨用户运行目录不可访问。
4. Tavily：使用已配置开发 key 做一次受预算限制的 Search 验证，再验证参数错误、凭据错误、限流/额度失败能形成配对工具消息；敏感 key 不出现在 trace。
5. 调度：验证不同 interval 产生不同 `next_fetch_at`，进程重启恢复计划，同一源并发领取只有一个执行者；检查旧缓存或缺失发布时间不会被标为“刚刚发布”。

以上是后续真实适配器与关键集成用例，不代表本次已执行这些验收。本阶段已完成官方源码/文档核查和表中四个 HTTP 抽样。
