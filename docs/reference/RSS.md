## 1. 第一批：优先直接接入

| 媒体       | 类型      | RSS                                                   |
| ---------- | --------- | ----------------------------------------------------- |
| 人民网     | 时政      | `https://www.people.com.cn/rss/politics.xml`          |
| 人民网     | 社会      | `https://www.people.com.cn/rss/society.xml`           |
| 人民网     | 国际      | `https://www.people.com.cn/rss/world.xml`             |
| 人民网     | 财经      | `https://www.people.com.cn/rss/finance.xml`           |
| 新华网     | 时政      | `http://www.xinhuanet.com/politics/news_politics.xml` |
| 新华网     | 国际      | `http://www.xinhuanet.com/world/news_world.xml`       |
| 新华网     | 地方      | `http://www.xinhuanet.com/local/news_province.xml`    |
| 新华网     | 金融      | `http://www.xinhuanet.com/finance/news_finance.xml`   |
| 新华网     | 财经      | `http://www.xinhuanet.com/fortune/news_fortune.xml`   |
| 新华网     | 法治      | `http://www.xinhuanet.com/legal/news_legal.xml`       |
| 新华网     | 科技      | `http://www.xinhuanet.com/tech/news_tech.xml`         |
| 中国新闻网 | 即时新闻  | `https://www.chinanews.com.cn/rss/scroll-news.xml`    |
| 中国新闻网 | 要闻      | `https://www.chinanews.com.cn/rss/importnews.xml`     |
| 中国新闻网 | 时政      | `https://www.chinanews.com.cn/rss/china.xml`          |
| 中国新闻网 | 国际      | `https://www.chinanews.com.cn/rss/world.xml`          |
| 中国新闻网 | 社会      | `https://www.chinanews.com.cn/rss/society.xml`        |
| 中国新闻网 | 财经      | `https://www.chinanews.com.cn/rss/finance.xml`        |
| 中国新闻网 | 教育      | `https://www.chinanews.com.cn/rss/edu.xml`            |
| 36氪       | 综合      | `https://36kr.com/feed`                               |
| 36氪       | 文章      | `https://36kr.com/feed-article`                       |
| 36氪       | 快讯      | `https://36kr.com/feed-newsflash`                     |
| IT之家     | 科技      | `https://www.ithome.com/rss/`                         |
| 界面新闻   | 综合      | `https://a.jiemian.com/index.php?m=article&a=rss`     |
| 少数派     | 科技/数码 | `https://sspai.com/feed`                              |
| Solidot    | 科技      | `https://www.solidot.org/index.rss`                   |
| 开源中国   | 科技/开发 | `https://www.oschina.net/news/rss`                    |

人民网这些旧版官方 RSS 地址目前仍会返回 XML 类型响应；新华网官方页面则直接列出了时政、国际、财经、法制、教育、体育、科技等大量 RSS 地址。

中国新闻网的 RSS 维护得相对完整，目前官方 RSS 中心列出了即时、要闻、时政、国际、社会、财经、生活、健康、文娱、体育、教育、法治等大量频道。([中国新闻网](https://www.chinanews.com/rss/?utm_source=chatgpt.com))

36氪现在也有专门的 RSS 订阅中心，官方给出的综合、文章、快讯地址分别就是 `/feed`、`/feed-article` 和 `/feed-newsflash`。([36氪](https://www.36kr.com/rss-center?utm_source=chatgpt.com))

IT之家目前网站仍保留 RSS 订阅入口，实际 `/rss/` 返回 XML；少数派、Solidot、开源中国的上述入口目前也仍返回 RSS/XML 类型内容。([IT之家](https://www.ithome.com/list/list_22.html?utm_source=chatgpt.com))

------

## 2. 新浪新闻 RSS

新浪的 RSS 系统比较老，但目前官方 RSS 页面仍然存在，而且部分 XML 端点仍然响应。

建议收：

```text
新浪新闻综合
https://rss.sina.com.cn/news/marquee/ddt.xml

国内新闻
https://rss.sina.com.cn/news/china/focus15.xml

国际新闻
https://rss.sina.com.cn/news/world/focus15.xml

社会新闻
https://rss.sina.com.cn/news/society/focus15.xml
```

新浪官方仍有完整 RSS 聚合中心，包括新闻、体育、科技、财经、军事、娱乐、汽车、教育等频道；上面的几个 XML 地址目前仍能返回 XML。([新浪网RSS频道](https://rss.sina.com.cn/?utm_source=chatgpt.com))

对于你的新闻系统，我会把新浪这些源标记为：

```yaml
reliability: legacy
```

因为这些是比较老的 RSS 基础设施。

------

## 3. 搜狐新闻 RSS

搜狐也保留了官方 RSS 中心。([搜狐新闻](https://news.sohu.com/rss.shtml?utm_source=chatgpt.com))

可以先配置：

```text
焦点新闻
http://rss.news.sohu.com/rss/focus.xml

国内新闻
http://rss.news.sohu.com/rss/guonei.xml

国际新闻
http://rss.news.sohu.com/rss/guoji.xml

社会新闻
http://rss.news.sohu.com/rss/shehui.xml

财经新闻
http://rss.news.sohu.com/rss/business.xml

IT新闻
http://rss.news.sohu.com/rss/it.xml

体育新闻
http://rss.news.sohu.com/rss/sports.xml

娱乐新闻
http://rss.news.sohu.com/rss/yule.xml
```

不过我在检查时搜狐部分 XML 请求存在超时，因此建议你的程序把它归类为：

```text
legacy RSS
+
失败自动降级
+
定期健康检查
```

而不要将其作为唯一新闻来源。

------

## 4. 央广网

央广网官方也有 RSS 订阅页面，提供国内、国际、科技、中国之声、经济之声等源。([央广网](https://www.cnr.cn/2009images/RSS/index.html?utm_source=chatgpt.com))

例如：

```text
国内新闻
http://www.cnr.cn/newscenter/gnxw/index_504031106.xml

国际新闻
http://www.cnr.cn/newscenter/gjxw/index_504031106.xml

科技新闻
http://www.cnr.cn/newscenter/kjxw/index_504031106.xml

图片新闻
http://www.cnr.cn/tupian/index_504031106.xml
```

它也是老 RSS 系统，所以同样建议：

```yaml
source_type: official_rss
status: legacy
health_check: true
```

------

## 5. 凤凰网

凤凰网现在仍能找到官方 RSS 订阅中心，官方页面列有综合、军事、历史、大陆、台湾、国际、社会、图片、评论、体育等分类。([凤凰网](https://news.ifeng.com/rss/?utm_source=chatgpt.com))

旧 RSS 地址包括：

```text
综合资讯
http://news.ifeng.com/rss/index.xml

大陆新闻
http://news.ifeng.com/pubres/rss/mainland/feed.xml

国际新闻
http://news.ifeng.com/pubres/rss/world/feed.xml

社会新闻
http://news.ifeng.com/pubres/rss/society/feed.xml

历史
http://news.ifeng.com/pubres/rss/history/feed.xml

图片
http://news.ifeng.com/pubres/rss/photo/feed.xml
```

但这一套也属于老系统。我会把凤凰、新浪、搜狐统一放入：

> Legacy Official RSS Provider

然后后台周期性检测。

------

# 6. 很重要：这些大型媒体更适合通过 RSSHub 补齐

这其实是你做国内新闻源时最重要的一部分。

很多现在很重要的媒体，没有稳定、公开、现代化的官方 RSS，例如：

| 媒体         | 推荐方式              |
| ------------ | --------------------- |
| 澎湃新闻     | RSSHub                |
| 财新网       | RSSHub                |
| 财联社       | RSSHub                |
| 财经网       | RSSHub                |
| 新京报       | RSSHub / 自建采集     |
| 南方周末     | RSSHub / FeedX        |
| 北京日报     | 官方数据接口/页面采集 |
| 第一财经     | 页面/API采集          |
| 证券时报     | 页面/API采集          |
| 上海证券报   | 页面采集              |
| 每日经济新闻 | 页面采集              |
| 经济观察报   | 页面采集              |
| 腾讯新闻     | RSSHub / API          |
| 网易新闻     | RSSHub / Legacy RSS   |
| 今日头条     | 不建议依赖 RSS        |
| 环球网       | RSSHub / 页面采集     |
| 观察者网     | RSSHub / 页面采集     |

例如 RSSHub 对**澎湃新闻**支持相当完整：

```text
首页头条
https://rsshub.app/thepaper/featured

时事
https://rsshub.app/thepaper/channel/25950

财经
https://rsshub.app/thepaper/channel/25951

科技
https://rsshub.app/thepaper/channel/119908

国际
https://rsshub.app/thepaper/channel/122908

评论
https://rsshub.app/thepaper/channel/-24
```

RSSHub 当前文档仍列出了这些澎湃新闻路由。([RSSHub](https://rsshub-doc.pages.dev/traditional-media?utm_source=chatgpt.com))

------

# 7. 财经新闻建议重点补这一组

你的新闻系统如果以后要做综合资讯，我建议财经单独搞一个 Provider Group。

### 财新

```text
最新文章
https://rsshub.app/caixin/latest

首页
https://rsshub.app/caixin/article

财新周刊
https://rsshub.app/caixin/weekly

金融监管
https://rsshub.app/caixin/finance/regulation
```

RSSHub 提供财新首页、最新文章、周刊以及不同财经栏目路由。([John Marques](https://john-marques.github.io/rsshub-docs/routes/traditional-media?utm_source=chatgpt.com))

### 财联社

```text
电报
https://rsshub.app/cls/telegraph

A股盘面
https://rsshub.app/cls/telegraph/watch

公司
https://rsshub.app/cls/telegraph/announcement

深度
https://rsshub.app/cls/depth/1000

热门
https://rsshub.app/cls/hot
```

当前 RSSHub 文档仍有这些财联社路由。([RSSHub](https://rsshub.netlify.app/zh/routes/finance?utm_source=chatgpt.com))

### 财经网

```text
https://rsshub.app/caijing/roll
```

也是 RSSHub 当前支持的财经媒体。([RSSHub](https://rsshub-doc.pages.dev/finance?utm_source=chatgpt.com))

------

# 8. 科技新闻再补这一组

你的项目本身和 AI / Agent 很相关，我非常建议额外建一个：

```text
TECH_CN
```

新闻池。

第一版可以：

```text
36氪
https://36kr.com/feed-newsflash

IT之家
https://www.ithome.com/rss/

少数派
https://sspai.com/feed

Solidot
https://www.solidot.org/index.rss

开源中国
https://www.oschina.net/news/rss

界面新闻
https://a.jiemian.com/index.php?m=article&a=rss
```

再通过网页采集/RSSHub增加：

```text
虎嗅
钛媒体
雷峰网
极客公园
机器之心
量子位
新智元
InfoQ 中文
CSDN
SegmentFault
腾讯科技
网易科技
新浪科技
```

这批源特别适合后面做：

```text
AI
Agent
LLM
编程
互联网
创业
投融资
科技产品
```

的个性化推送。

------

# 9. 我建议你第一版直接采用的 30 个 Feed

如果让我替你的项目选，我不会一次塞几百个源。先从这 **30 个**开始：

```text
# ===== 央媒 / 综合 =====

人民网-时政
https://www.people.com.cn/rss/politics.xml

人民网-社会
https://www.people.com.cn/rss/society.xml

人民网-国际
https://www.people.com.cn/rss/world.xml

新华网-时政
http://www.xinhuanet.com/politics/news_politics.xml

新华网-国际
http://www.xinhuanet.com/world/news_world.xml

新华网-财经
http://www.xinhuanet.com/fortune/news_fortune.xml

新华网-科技
http://www.xinhuanet.com/tech/news_tech.xml

中新社-即时
https://www.chinanews.com.cn/rss/scroll-news.xml

中新网-要闻
https://www.chinanews.com.cn/rss/importnews.xml

中新网-时政
https://www.chinanews.com.cn/rss/china.xml

中新网-国际
https://www.chinanews.com.cn/rss/world.xml

中新网-社会
https://www.chinanews.com.cn/rss/society.xml

中新网-财经
https://www.chinanews.com.cn/rss/finance.xml


# ===== 门户 =====

新浪-国内
https://rss.sina.com.cn/news/china/focus15.xml

新浪-国际
https://rss.sina.com.cn/news/world/focus15.xml

新浪-社会
https://rss.sina.com.cn/news/society/focus15.xml

搜狐-国内
http://rss.news.sohu.com/rss/guonei.xml

搜狐-国际
http://rss.news.sohu.com/rss/guoji.xml


# ===== 财经 =====

财新
https://rsshub.app/caixin/latest

财联社
https://rsshub.app/cls/telegraph

财经网
https://rsshub.app/caijing/roll

澎湃财经
https://rsshub.app/thepaper/channel/25951


# ===== 科技 =====

36氪-综合
https://36kr.com/feed

36氪-快讯
https://36kr.com/feed-newsflash

IT之家
https://www.ithome.com/rss/

Solidot
https://www.solidot.org/index.rss

少数派
https://sspai.com/feed

开源中国
https://www.oschina.net/news/rss

澎湃科技
https://rsshub.app/thepaper/channel/119908

界面新闻
https://a.jiemian.com/index.php?m=article&a=rss
```

这已经足够你的 MVP 每天获得相当大的候选新闻池。

------

## 10. 后端不要直接把 URL 写死

建议你的数据库设计成：

```text
news_source
├── id
├── name
├── publisher
├── category
├── url
├── source_type
├── country
├── language
├── priority
├── credibility_level
├── fetch_interval
├── enabled
├── last_fetch_at
├── last_success_at
├── consecutive_failures
└── status
```

例如：

```json
{
  "name": "中国新闻网-即时新闻",
  "publisher": "中国新闻网",
  "category": "general",
  "url": "https://www.chinanews.com.cn/rss/scroll-news.xml",
  "source_type": "OFFICIAL_RSS",
  "country": "CN",
  "language": "zh-CN",
  "priority": 100,
  "fetch_interval": 300,
  "enabled": true
}
```

然后区分：

```text
OFFICIAL_RSS
RSSHUB
THIRD_PARTY_RSS
WEB_CRAWLER
NEWS_API
SEARCH
```

这一点以后会非常有用。

### 最终我建议你的国内新闻源结构

```text
中国新闻源
│
├── 央媒
│   ├── 人民网
│   ├── 新华网
│   ├── 中国新闻网
│   └── 央广网
│
├── 综合门户
│   ├── 新浪
│   ├── 搜狐
│   ├── 网易
│   ├── 腾讯
│   └── 凤凰
│
├── 新媒体
│   ├── 澎湃
│   ├── 界面
│   ├── 新京报
│   └── 南方周末
│
├── 财经
│   ├── 财新
│   ├── 财联社
│   ├── 第一财经
│   ├── 财经网
│   ├── 证券时报
│   └── 每日经济新闻
│
└── 科技
    ├── 36氪
    ├── IT之家
    ├── 虎嗅
    ├── 雷峰网
    ├── 机器之心
    ├── 量子位
    ├── 少数派
    ├── Solidot
    └── 开源中国
```

其中**央媒优先官方 RSS，现代媒体优先 RSSHub/API，确实没有稳定 RSS 的再用定向爬虫**。这样会比强行给所有媒体找 RSS 稳定得多。

如果你下一步要直接开始实现，我可以继续给你整理一份 **100+ 国内新闻 RSS/RSSHub 数据源清单**，按「综合、时政、国际、财经、科技、AI、汽车、体育、娱乐」分类，并直接给你生成可导入数据库的 `news_sources.json / YAML / OPML`。