"""Real MySQL/Docker checks are opt-in and never replaced with in-memory fakes."""

import json
import os
import subprocess
import sys
import uuid

import httpx
import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from zhigenews.harness.errors import HarnessError
from zhigenews.harness.persistence import mysql_persistence
from zhigenews.harness.sandbox import DockerSandbox
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
def test_real_sandbox_readonly_networkless_and_output(tmp_path):
    rss, workspace = tmp_path / "rss", tmp_path / "workspace"
    rss.mkdir()
    (workspace / "output").mkdir(parents=True)
    (rss / "fixture").write_text("authorized synthetic content")
    sandbox = DockerSandbox(rss, workspace)
    result = sandbox.run(
        'cat /rss/fixture; id -u; test ! -e /var/run/docker.sock; test -z "$OPENAI_API_KEY"; test ! -w /workspace/output',
        timeout=20,
    )
    assert result["ok"] and "65534" in result["output"]
    assert not sandbox.run("echo bypass > /workspace/output/file")["ok"]
    assert not (workspace / "output" / "file").exists()
    result = sandbox.run(
        "python -c 'import socket; socket.create_connection((\"1.1.1.1\", 80), 1)'", timeout=5
    )
    assert not result["ok"]
    result = sandbox.run("python -c 'print(\"x\" * 100000)'", timeout=10)
    assert result["truncated"] and len(result["output"].encode()) <= 16384
    result = sandbox.run("sleep 10", timeout=1)
    assert result["timeout"]
