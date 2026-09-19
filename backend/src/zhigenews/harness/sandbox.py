"""Docker-only shell execution: no host shell fallback and no writable mounts."""

from __future__ import annotations

import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from .errors import HarnessError, RunCancelled

SANDBOX_IMAGE = "python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"


class DockerSandbox:
    def __init__(
        self, rss_root: Path, workspace_root: Path, image: str = SANDBOX_IMAGE, *, max_bytes: int = 16384
    ):
        self.rss_root, self.workspace_root = Path(rss_root).resolve(), Path(workspace_root).resolve()
        self.image, self.max_bytes = image, max_bytes

    def run(
        self,
        command: str,
        cwd: str = "/workspace",
        timeout: int = 10,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> dict:
        if not command or len(command) > 8192:
            raise HarnessError("INVALID_COMMAND", "命令长度须在 1–8192 字符之间。")
        if cwd not in ("/workspace", "/workspace/output", "/workspace/inputs", "/rss", "/tmp"):
            raise HarnessError("INVALID_PATH", "沙箱工作目录无效。")
        timeout = min(max(timeout, 1), 30)
        name = "zhigenews-sandbox-" + uuid.uuid4().hex
        args = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--user",
            "65534:65534",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "256m",
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=32m",
            "--mount",
            f"type=bind,src={self.rss_root},dst=/rss,readonly",
            "--mount",
            f"type=bind,src={self.workspace_root},dst=/workspace,readonly",
            "--workdir",
            cwd,
            self.image,
            "bash",
            "-c",
            command,
        ]
        started, captured, total = time.monotonic(), bytearray(), [0]
        try:
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
            )
        except OSError:
            raise HarnessError("SANDBOX_UNAVAILABLE", "Docker Linux 命令沙箱不可用。") from None

        def drain():
            assert process.stdout
            while chunk := process.stdout.read(4096):
                total[0] += len(chunk)
                captured.extend(chunk[: max(0, self.max_bytes - len(captured))])

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        timed_out = was_cancelled = False
        try:
            while process.poll() is None:
                was_cancelled = cancelled()
                timed_out = time.monotonic() - started >= timeout
                if timed_out or was_cancelled:
                    subprocess.run(
                        ["docker", "rm", "-f", name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=10,
                        check=False,
                    )
                    process.kill()
                    break
                time.sleep(0.05)
            process.wait(timeout=10)
            reader.join(timeout=2)
        finally:
            if process.poll() is None:
                process.kill()
            if process.stdout:
                process.stdout.close()
        if was_cancelled:
            raise RunCancelled()
        if process.returncode == 125:
            raise HarnessError("SANDBOX_UNAVAILABLE", "Docker 拒绝启动受限 Linux 沙箱，请检查服务与镜像。")
        decoded = captured.decode("utf-8", errors="replace").encode("utf-8")
        return {
            "ok": process.returncode == 0 and not timed_out,
            "code": "TIMEOUT" if timed_out else "OK" if process.returncode == 0 else "COMMAND_FAILED",
            "output": decoded[: self.max_bytes].decode("utf-8", errors="ignore"),
            "exitCode": process.returncode,
            "durationMs": round((time.monotonic() - started) * 1000),
            "truncated": total[0] > self.max_bytes or len(decoded) > self.max_bytes,
            "timeout": timed_out,
        }
