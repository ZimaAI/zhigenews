import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


class FeedTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {"text": "", "url": ""}
        elif tag == "a" and self.cell is not None:
            self.cell["url"] = dict(attrs).get("title", "")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if len(self.row) == 3 and self.row[1]["url"]:
                self.rows.append({"name": self.row[0]["text"].strip(), "url": self.row[1]["url"]})
            self.row = None


root = Path(__file__).resolve().parents[2]
parser = FeedTable()
parser.feed((Path(__file__).parent / "juejin.html").read_text(encoding="utf-8"))
assert len(parser.rows) == 340, len(parser.rows)
assert len({row["url"] for row in parser.rows}) == 340
serialized = json.dumps(parser.rows, ensure_ascii=False, separators=(",", ":"))
signature = 2166136261
for char in serialized:
    signature = ((signature ^ ord(char)) * 16777619) & 0xFFFFFFFF
# Independently extracted from the rendered browser table.
assert len(serialized) == 22571 and signature == 483413151, (len(serialized), signature)
sources = [{"id": "rss-chinanews", "name": "中国新闻网 · 即时新闻", "url": "https://www.chinanews.com.cn/rss/scroll-news.xml"}]
for row in parser.rows:
    host = urlsplit(row["url"]).hostname
    assert urlsplit(row["url"]).scheme in {"http", "https"} and host
    sources.append({
        "id": "rss-" + host.removeprefix("www.").replace(".", "-") + "-" + hashlib.sha256(row["url"].encode()).hexdigest()[:12],
        "name": row["name"] or row["url"],
        "url": row["url"],
    })
document = {
    "reference_url": "https://juejin.cn/post/7459966392429101067",
    "retrieved_on": "2026-09-19",
    "article_source_count": len(parser.rows),
    "configured_interval_seconds": 1800,
    "sources": sources,
}
destination = root / "backend/src/zhigenews/ingestion/default-rss-sources.json"
destination.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"article_rows": len(parser.rows), "default_rss_sources": len(sources), "unnamed": [r for r in parser.rows if not r["name"]]}, ensure_ascii=False))
