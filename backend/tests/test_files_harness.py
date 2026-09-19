import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from zhigenews.harness.errors import HarnessError
from zhigenews.harness.files import FileService


@pytest.fixture
def files(tmp_path):
    (tmp_path / "rss").mkdir()
    (tmp_path / "workspace" / "output").mkdir(parents=True)
    (tmp_path / "workspace" / "inputs").mkdir()
    return FileService(tmp_path / "rss", tmp_path / "workspace")


@pytest.mark.parametrize(
    "path",
    [
        "../x",
        "/workspace/../x",
        "/workspace/output/../../x",
        "C:/Users/key",
        "//server/share",
        "/workspace\\output\\x",
        "/workspace2/output/x",
        "/etc/passwd",
        "/workspace/%2e%2e/key",
        "/workspace/output/x\x00",
    ],
)
def test_reject_untrusted_path(files, path):
    with pytest.raises(HarnessError, match="路径|目录"):
        files.read_file(path)


def test_partial_read_hash_cas_and_exclusive_create(files):
    path = files.roots["workspace"] / "output" / "brief.txt"
    path.write_bytes("第一行\n第二行\n末尾".encode())
    first = files.read_file("/workspace/output/brief.txt", 1, 1)
    assert first["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert first["totalLines"] == 3 and first["nextLine"] == 2
    assert first["lines"] == [{"line": 1, "text": "第一行"}]
    path.write_text("changed\n", "utf-8")
    with pytest.raises(HarnessError) as exc:
        files.write_file("/workspace/output/brief.txt", "overwrite", first["sha256"])
    assert exc.value.code == "FILE_CHANGED"
    latest = files.read_file("/workspace/output/brief.txt")
    files.write_file("/workspace/output/brief.txt", "updated", latest["sha256"])
    with pytest.raises(HarnessError) as exc:
        files.write_file("/workspace/output/brief.txt", "bad", create_new=True)
    assert exc.value.code == "FILE_ALREADY_EXISTS"
    with pytest.raises(HarnessError):
        files.write_file("/rss/new.txt", "forbidden", create_new=True)
    with pytest.raises(HarnessError):
        files.write_file("/workspace/inputs/new.txt", "forbidden", create_new=True)
    with pytest.raises(HarnessError):
        files.write_file("/workspace/output/missing/new.txt", "bad", create_new=True)


def test_two_actor_overwrites_only_one_succeeds(files):
    files.write_file("/workspace/output/x", "old", create_new=True)
    other = FileService(files.roots["rss"], files.roots["workspace"], actor="child")
    read_a, read_b = files.read_file("/workspace/output/x"), other.read_file("/workspace/output/x")

    def write(actor, sha):
        try:
            return actor.write_file("/workspace/output/x", actor.actor, sha)["ok"]
        except HarnessError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as executor:
        result = list(
            executor.map(lambda pair: write(*pair), [(files, read_a["sha256"]), (other, read_b["sha256"])])
        )
    assert sorted(map(str, result)) == ["FILE_CHANGED", "True"]


def test_write_execution_replay_and_persistent_read_ledger(files):
    first = files.write_file("/workspace/output/x", "old", create_new=True, execution_id="tool-1")
    restored = FileService(files.roots["rss"], files.roots["workspace"])
    assert restored.write_file("/workspace/output/x", "old", create_new=True, execution_id="tool-1") == first
    restored.read_file("/workspace/output/x")
    restored = FileService(files.roots["rss"], files.roots["workspace"])
    assert restored.versions()["/workspace/output/x"] == first["sha256"]
    with pytest.raises(HarnessError):
        restored.write_file("/workspace/output/x", "changed", create_new=True, execution_id="tool-1")


def test_outputs_bound_long_line(files):
    (files.roots["workspace"] / "output" / "long").write_text("X" * 1000000 + "\nend", "utf-8")
    result = files.read_file("/workspace/output/long")
    assert result["truncated"] and result["nextLine"] == 1
    assert len(json.dumps(result).encode()) <= 16384
    assert result["size"] == (files.roots["workspace"] / "output" / "long").stat().st_size


def test_link_escape_rejected(files, tmp_path):
    external = tmp_path / "outside"
    external.mkdir()
    (external / "secret").write_text("secret")
    try:
        (files.roots["workspace"] / "output" / "link").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Windows lacks symlink privilege; Linux container test covers links")
    with pytest.raises(HarnessError):
        files.read_file("/workspace/output/link/secret")


def test_write_recovers_receipt_after_interrupted_commit(files):
    original_save = files._save
    count = [0]

    def interrupted(data):
        count[0] += 1
        if count[0] == 2:
            raise RuntimeError("synthetic crash after file write")
        original_save(data)

    files._save = interrupted
    with pytest.raises(RuntimeError):
        files.write_file("/workspace/output/x", "persisted", create_new=True, execution_id="c")
    restored = FileService(files.roots["rss"], files.roots["workspace"])
    assert restored.write_file("/workspace/output/x", "persisted", create_new=True, execution_id="c")["ok"]
    assert (files.roots["workspace"] / "output" / "x").read_text() == "persisted"


@pytest.mark.skipif(
    os.environ.get("HARNESS_TEST_DOCKER") != "1",
    reason="requires actual Linux container for descriptor and symlink checks",
)
def test_linux_descriptor_path_swap_and_cas():
    import filelock

    from zhigenews.harness.sandbox import SANDBOX_IMAGE

    backend = Path(__file__).resolve().parents[1]
    dependencies = Path(filelock.__file__).resolve().parent.parent
    script = r"""
import sys, types, pathlib, tempfile, os
sys.path.insert(0, '/deps')
for name, path in [('zhigenews','/code/src/zhigenews'), ('zhigenews.harness','/code/src/zhigenews/harness')]:
    module=types.ModuleType(name); module.__path__=[path]; sys.modules[name]=module
from zhigenews.harness.files import FileService
from zhigenews.harness.errors import HarnessError
for operation in ('read', 'write', 'list'):
    with tempfile.TemporaryDirectory() as temp:
        base=pathlib.Path(temp); rss=base/'rss'; workspace=base/'workspace'; outside=base/'outside'
        rss.mkdir(); (workspace/'output').mkdir(parents=True); outside.mkdir()
        (outside/'secret').write_text('HOST SECRET'); (workspace/'output'/'secret').write_text('authorized')
        files=FileService(rss,workspace); prior=files.read_file('/workspace/output/secret')
        original=files._parts
        def raced(path, **kwargs):
            parsed=original(path, **kwargs)
            (workspace/'output').rename(workspace/'original')
            (workspace/'output').symlink_to(outside, target_is_directory=True)
            return parsed
        files._parts=raced
        try:
            if operation=='read': files.read_file('/workspace/output/secret')
            elif operation=='write': files.write_file('/workspace/output/secret','overwrite',prior['sha256'])
            else: files.list_dir('/workspace/output')
            raise AssertionError('path swap escaped: '+operation)
        except HarnessError:
            pass
        assert (outside/'secret').read_text()=='HOST SECRET'
with tempfile.TemporaryDirectory() as temp:
    root=pathlib.Path(temp); (root/'rss').mkdir(); (root/'work'/'output').mkdir(parents=True)
    files=FileService(root/'rss',root/'work'); files.write_file('/workspace/output/a','one',create_new=True)
    assert (root/'work'/'output'/'a').stat().st_mode & 0o004, 'sandbox UID cannot read output'
    version=files.read_file('/workspace/output/a')['sha256']; files.write_file('/workspace/output/a','two',version)
    assert files.read_file('/workspace/output/a')['lines'][0]['text']=='two'
print('Linux O_NOFOLLOW path replacement and CAS passed')
"""
    args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,size=32m",
        "--mount",
        f"type=bind,src={backend},dst=/code,readonly",
        "--mount",
        f"type=bind,src={dependencies},dst=/deps,readonly",
        SANDBOX_IMAGE,
        "python",
        "-c",
        script,
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "passed" in result.stdout
