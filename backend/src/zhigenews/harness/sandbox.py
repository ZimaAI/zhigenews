"""Docker-only shell execution with read-only news and an isolated writable workspace."""

from __future__ import annotations

import os
import stat
import subprocess
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Callable

from .errors import HarnessError, RunCancelled
from .files import authorized_news_roots

SANDBOX_IMAGE = "python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"


class DockerSandbox:
    def __init__(
        self,
        rss_root: Path,
        workspace_root: Path,
        image: str = SANDBOX_IMAGE,
        *,
        max_bytes: int = 16384,
        news_roots: dict[str, Path] | None = None,
    ):
        self.rss_root, self.workspace_root = Path(rss_root).resolve(), Path(workspace_root).resolve()
        self.news_roots = authorized_news_roots(news_roots) if news_roots is not None else None
        self.image, self.max_bytes = image, max_bytes
        self._prepare_workspace()

    def _prepare_workspace(self) -> None:
        if os.name != "posix" or os.getuid() != 0:
            return
        # Root-owned host directories (usually 0755) must actually be writable
        # by the non-root container. Stay inside this run and never follow links.
        for _, _, files, directory_fd in os.fwalk(self.workspace_root, follow_symlinks=False):
            os.fchown(directory_fd, 65534, 65534)
            for filename in files:
                try:
                    fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                except OSError:
                    continue
                try:
                    info = os.fstat(fd)
                    if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                        os.fchown(fd, 65534, 65534)
                finally:
                    os.close(fd)

    def _validate_cwd(self, cwd: str) -> None:
        if (
            not cwd.startswith("/")
            or cwd.startswith("//")
            or any(char in cwd for char in ("\\", "\x00", ":", "%", "~"))
            or any(part in ("..", ".") for part in cwd.split("/"))
        ):
            raise HarnessError("INVALID_PATH", "沙箱工作目录无效。")
        parts = PurePosixPath(cwd).parts[1:]
        if parts == ("tmp",) or (parts == ("news",) and self.news_roots is not None):
            return
        if parts and parts[0] == "workspace":
            root, relative = self.workspace_root, parts[1:]
        elif parts and parts[0] == "rss" and self.news_roots is None:
            root, relative = self.rss_root, parts[1:]
        elif len(parts) >= 2 and parts[0] == "news" and parts[1] in (self.news_roots or {}):
            root, relative = self.news_roots[parts[1]], parts[2:]
        else:
            raise HarnessError("INVALID_PATH", "沙箱工作目录不属于本次运行的授权目录。")
        candidate = root
        for part in relative:
            candidate = candidate / part
            try:
                info = candidate.lstat()
            except OSError:
                raise HarnessError("INVALID_PATH", "沙箱工作目录不存在。") from None
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024
            ):
                raise HarnessError("INVALID_PATH", "沙箱工作目录不得经过符号链接或重解析点。")
        if not candidate.is_dir():
            raise HarnessError("INVALID_PATH", "沙箱工作目录不存在。")

    def run(
        self,
        command: str,
        cwd: str = "/workspace",
        timeout: int = 10,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> dict:
        if not command or len(command) > 8192:
            raise HarnessError("INVALID_COMMAND", "命令长度须在 1–8192 字符之间。")
        self._validate_cwd(cwd)
        self._prepare_workspace()
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
            f"{os.getuid()}:{os.getgid()}" if os.name == "posix" and os.getuid() else "65534:65534",
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
            f"type=bind,src={self.workspace_root},dst=/workspace",
        ]
        if self.news_roots is None:
            args.extend(["--mount", f"type=bind,src={self.rss_root},dst=/rss,readonly"])
        else:
            args.extend(["--tmpfs", "/news:ro,nosuid,nodev,noexec,size=1m,mode=555"])
            for source, root in sorted(self.news_roots.items()):
                args.extend(["--mount", f"type=bind,src={root},dst=/news/{source},readonly"])
        args.extend(
            [
                "--workdir",
                cwd,
                self.image,
                "bash",
                "-c",
                command,
            ]
        )
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
