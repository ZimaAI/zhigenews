"""Real MySQL/Docker checks are opt-in and never replaced with in-memory fakes."""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from zhigenews.harness.errors import HarnessError
from zhigenews.harness.persistence import mysql_persistence
from zhigenews.harness.sandbox import SANDBOX_IMAGE, DockerSandbox
from zhigenews.harness.search import TavilySearch


def test_tavily_bounded_synthetic_response():
    observed = []

    def respond(request):
        observed.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "T" * 900, "url": f"https://example.com/{i}", "content": "C" * 10000}
                    for i in range(20)
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        evidence = {}
        search = TavilySearch("synthetic-key", client=client, max_calls=1, evidence=evidence)
        result = search.search("AI news", 500)
        assert observed[0]["max_results"] == 10
        assert len(json.dumps(result, ensure_ascii=False).encode()) < 24576
        assert evidence and all(e["published_at"] is None for e in evidence.values())
        with pytest.raises(HarnessError) as exc:
            search.search("again")
        assert exc.value.code == "SEARCH_BUDGET"


@pytest.mark.skipif(
    not os.environ.get("HARNESS_TEST_MYSQL_URL"), reason="requires an actual MySQL 8 test database"
)
def test_mysql_pending_writes_namespaces_and_restart():
    url = os.environ["HARNESS_TEST_MYSQL_URL"]
    thread = "harness-test-" + uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}
    child_config = {"configurable": {"thread_id": thread, "checkpoint_ns": "child"}}
    with mysql_persistence(url, setup=True) as saver:
        cp = empty_checkpoint()
        cp["channel_values"] = {"value": {"unicode": "中文", "nested": [1, None]}}
        cp["channel_versions"] = {"value": "1"}
        config = saver.put(config, cp, {"source": "input", "step": -1, "parents": {}}, {"value": "1"})
        saver.put_writes(config, [("value", {"result": 1})], "task-a")
        saver.put_writes(config, [("value", {"result": 2})], "task-b")
        child = empty_checkpoint()
        child["channel_values"] = {"value": "child"}
        child["channel_versions"] = {"value": "1"}
        saver.put(child_config, child, {"source": "input", "step": -1, "parents": {}}, {"value": "1"})
    script = "from zhigenews.harness.persistence import mysql_persistence; import os,json;\nwith mysql_persistence(os.environ['HARNESS_TEST_MYSQL_URL']) as s:\n t=s.get_tuple({'configurable':{'thread_id':os.environ['HARNESS_THREAD'],'checkpoint_ns':''}}); print(json.dumps({'value':t.checkpoint['channel_values']['value'],'pending':len(t.pending_writes)}))"
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "HARNESS_THREAD": thread},
        text=True,
        capture_output=True,
        check=True,
    )
    restored = json.loads(result.stdout)
    assert restored["value"]["unicode"] == "中文" and restored["pending"] == 2
    with mysql_persistence(url) as saver:
        assert saver.get_tuple(child_config).checkpoint["channel_values"]["value"] == "child"
        assert len(list(saver.list({"configurable": {"thread_id": thread}}))) == 2
        saver.delete_thread(thread)
        assert saver.get_tuple(config) is None


class CounterState(TypedDict):
    count: int


@pytest.mark.skipif(not os.environ.get("HARNESS_TEST_MYSQL_URL"), reason="requires real MySQL")
def test_mysql_actual_graph_interrupt_resume():
    url = os.environ["HARNESS_TEST_MYSQL_URL"]
    thread = "harness-graph-test-" + uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread}}

    def build(saver):
        graph = StateGraph(CounterState)
        graph.add_node("first", lambda state: {"count": state["count"] + 1})
        graph.add_node("second", lambda state: {"count": state["count"] + 10})
        graph.add_edge(START, "first")
        graph.add_edge("first", "second")
        graph.add_edge("second", END)
        return graph.compile(checkpointer=saver, interrupt_before=["second"])

    with mysql_persistence(url) as saver:
        assert build(saver).invoke({"count": 0}, config)["count"] == 1
    with mysql_persistence(url) as saver:
        assert build(saver).invoke(None, config)["count"] == 11
        saver.delete_thread(thread)


@pytest.mark.skipif(
    os.environ.get("HARNESS_TEST_DOCKER") != "1",
    reason="requires actual Docker Linux daemon and sandbox image",
)
def test_real_sandbox_news_readonly_workspace_writable_and_networkless(tmp_path):
    rss, workspace = tmp_path / "rss", tmp_path / "workspace"
    (rss / "enabled" / "snapshots").mkdir(parents=True)
    (rss / "disabled").mkdir()
    (workspace / "output").mkdir(parents=True)
    (workspace / "inputs").mkdir()
    (tmp_path / "another-run").mkdir()
    (tmp_path / "another-run" / "secret").write_text("another run")
    (rss / "enabled" / "fixture").write_text("authorized synthetic content")
    sandbox = DockerSandbox(rss, workspace, news_roots={"enabled": rss / "enabled"})
    result = sandbox.run(
        'set -e; cat /news/enabled/fixture; test "$(id -u)" -ne 0; '
        'test ! -e /var/run/docker.sock; test -z "$OPENAI_API_KEY"; '
        "test ! -e /news/disabled; test ! -e /rss; test ! -e /another-run; "
        "test ! -e /.workspace.harness; "
        "echo draft > /workspace/draft; echo input > /workspace/inputs/note; "
        "mkdir /workspace/notes; echo output > /workspace/output/file",
        timeout=20,
    )
    assert result["ok"], result["output"]
    assert (workspace / "draft").read_text().strip() == "draft"
    assert (workspace / "inputs" / "note").read_text().strip() == "input"
    assert (workspace / "output" / "file").read_text().strip() == "output"
    assert sandbox.run("echo nested > note", cwd="/workspace/notes")["ok"]
    assert sandbox.run("pwd", cwd="/news/enabled/snapshots")["ok"]
    for command in (
        "echo bypass > /news/enabled/fixture",
        "touch /news/enabled/new",
        "rm /news/enabled/fixture",
    ):
        assert not sandbox.run(command)["ok"]
    result = sandbox.run(
        "python -c 'import socket; socket.create_connection((\"1.1.1.1\", 80), 1)'", timeout=5
    )
    assert not result["ok"]
    result = sandbox.run("python -c 'print(\"x\" * 100000)'", timeout=10)
    assert result["truncated"] and len(result["output"].encode()) <= 16384
    result = sandbox.run("sleep 10", timeout=1)
    assert result["timeout"]


@pytest.mark.skipif(
    os.environ.get("HARNESS_TEST_DOCKER") != "1",
    reason="requires actual Linux filesystem permissions for collected news",
)
def test_linux_collected_news_is_readable_by_nonroot_sandbox_user():
    backend = Path(__file__).resolve().parents[1]
    dependencies = Path(httpx.__file__).resolve().parent.parent
    script = r"""
import sys, types, pathlib, subprocess
from datetime import UTC, datetime
sys.path.insert(0, '/deps')
module=types.ModuleType('zhigenews'); module.__path__=['/code/src/zhigenews']; sys.modules['zhigenews']=module
import httpx
from zhigenews.ingestion import fetch_source, source_news_directory
storage=pathlib.Path('/news')
source={'id':'synthetic-source','kind':'rss','name':'Synthetic','url':'https://example.test/feed.xml'}
raw=b'<rss version="2.0"><channel><title>Synthetic feed</title><item><guid>one</guid><title>Synthetic collected news</title><link>https://example.test/article</link><pubDate>Fri, 18 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>'
with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=raw))) as client:
    result=fetch_source(source, storage, client=client, now=datetime(2026,9,18,16,tzinfo=UTC), jitter_ratio=0)
assert result['attempt']['outcome']=='published', result
news_root=source_news_directory(result['source'], storage)
assert news_root.stat().st_uid==0 and news_root.stat().st_mode & 0o777==0o755
paths=[news_root/'index.json', storage/result['snapshot']['parsed_path'], storage/result['snapshot']['raw_path']]
assert all(path.stat().st_uid==0 for path in paths)
read=subprocess.run(
    [sys.executable,'-c',"from pathlib import Path; import sys; [print(Path(p).read_text()) for p in sys.argv[1:]]", *map(str,paths)],
    user=65534, group=65534, extra_groups=(), capture_output=True, text=True,
)
assert read.returncode==0, read.stderr
assert read.stdout.count('Synthetic collected news')>=3, read.stdout
print('Root-collected index, parsed news and raw source readable by sandbox UID passed')
"""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,size=32m",
            "--tmpfs",
            "/news:rw,size=32m,mode=755",
            "--mount",
            f"type=bind,src={backend},dst=/code,readonly",
            "--mount",
            f"type=bind,src={dependencies},dst=/deps,readonly",
            SANDBOX_IMAGE,
            "python",
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "passed" in result.stdout
