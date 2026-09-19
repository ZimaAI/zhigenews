"""Virtual files, streaming reads and a process-safe compare-and-swap writer.

Linux uses directory descriptors and O_NOFOLLOW throughout each operation. On
Windows all reparse points are rejected; Linux remains the deployment boundary.
Only this service writes persistent run files; bash sees read-only mounts.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from filelock import FileLock

from .errors import HarnessError


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FileService:
    def __init__(
        self, rss_root: Path, workspace_root: Path, actor: str = "main", *, output_bytes: int = 16384
    ):
        self.roots = {
            "rss": Path(rss_root).resolve(strict=True),
            "workspace": Path(workspace_root).resolve(strict=True),
        }
        self.actor = actor
        self.output_bytes = output_bytes
        self.metadata = self.roots["workspace"].parent / ("." + self.roots["workspace"].name + ".harness")
        self.metadata.mkdir(exist_ok=True)
        self.lock = FileLock(str(self.metadata / "files.lock"))
        self.ledger_file = self.metadata / "files.json"

    def _parts(self, virtual: str, *, write: bool = False) -> tuple[Path, tuple[str, ...], str]:
        if (
            not isinstance(virtual, str)
            or len(virtual) > 1024
            or not virtual.startswith("/")
            or virtual.startswith("//")
            or any(x in virtual for x in ("\\", "\x00", ":", "%", "~"))
        ):
            raise HarnessError("INVALID_PATH", "仅支持 /rss 和 /workspace 的 POSIX 虚拟路径。")
        raw = virtual.split("/")
        if any(p in ("..", ".") for p in raw):
            raise HarnessError("INVALID_PATH", "路径不得包含父目录或相对目录段。")
        parts = PurePosixPath(virtual).parts[1:]
        if not parts or parts[0] not in self.roots:
            raise HarnessError("INVALID_PATH", "路径不属于本次运行的授权目录。")
        if write and (parts[0] != "workspace" or len(parts) < 3 or parts[1] != "output"):
            raise HarnessError("PERMISSION_DENIED", "只有 /workspace/output 下的文件可写。")
        root, rel = self.roots[parts[0]], parts[1:]
        candidate = root
        for part in rel:
            candidate = candidate / part
            try:
                info = candidate.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
                    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024
                ):
                    raise HarnessError("INVALID_PATH", "禁止访问符号链接或重解析点。")
            except FileNotFoundError:
                pass
        if not candidate.resolve(strict=False).is_relative_to(root):
            raise HarnessError("INVALID_PATH", "解析路径超出授权目录。")
        return root, rel, "/" + "/".join(parts)

    @contextmanager
    def _parent(self, root: Path, rel: tuple[str, ...]):
        if not rel:
            raise HarnessError("INVALID_PATH", "操作需要文件路径。")
        if os.name == "posix":
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for part in rel[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = child
                yield fd, rel[-1]
            finally:
                os.close(fd)
        else:
            parent = root.joinpath(*rel[:-1])
            if not parent.is_dir():
                raise HarnessError("FILE_NOT_FOUND", "父目录不存在。")
            yield None, str(parent / rel[-1])

    def _open(self, name: str, flags: int, parent_fd: int | None) -> int:
        # The unprivileged read-only sandbox must be able to read this run's output.
        # Authorization is the isolated mount, not the host file owner identity.
        fd = os.open(name, flags | getattr(os, "O_NOFOLLOW", 0), 0o644, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise HarnessError("INVALID_PATH", "只允许普通文本文件。")
        return fd

    def _ledger(self) -> dict:
        return (
            json.loads(self.ledger_file.read_text("utf-8"))
            if self.ledger_file.exists()
            else {"reads": {}, "executions": {}}
        )

    def _save(self, data: dict) -> None:
        temporary = self.metadata / "files.json.tmp"
        temporary.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        os.replace(temporary, self.ledger_file)

    def versions(self) -> dict:
        with self.lock:
            return dict(self._ledger()["reads"].get(self.actor, {}))

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> dict:
        if start_line < 1 or end_line is not None and end_line < start_line:
            raise HarnessError("INVALID_RANGE", "行号从 1 开始，结束行不得小于起始行。")
        end_line = min(end_line or start_line + 199, start_line + 199)
        root, rel, virtual = self._parts(path)
        with self.lock:
            try:
                with self._parent(root, rel) as (parent_fd, name):
                    fd = self._open(name, os.O_RDONLY, parent_fd)
                    with os.fdopen(fd, "rb") as stream:
                        digest, size, lines, selected, used, next_line = hashlib.sha256(), 0, 0, [], 0, None
                        # readline(size) bounds allocation even for hostile single-line files.
                        pending, line_no = bytearray(), 1
                        while chunk := stream.read(65536):
                            digest.update(chunk)
                            size += len(chunk)
                            for piece in chunk.splitlines(keepends=True):
                                if start_line <= line_no <= end_line and len(pending) < self.output_bytes + 1:
                                    pending.extend(piece[: self.output_bytes + 1 - len(pending)])
                                if piece.endswith(b"\n"):
                                    lines = line_no
                                    if start_line <= line_no <= end_line:
                                        if used + len(pending) <= self.output_bytes - 1024:
                                            text = pending.decode("utf-8", errors="replace").rstrip("\r\n")
                                            item = {"line": line_no, "text": text}
                                            encoded_size = len(json.dumps(item, ensure_ascii=False).encode())
                                            if used + encoded_size <= self.output_bytes - 1024:
                                                selected.append(item)
                                                used += encoded_size
                                            elif next_line is None:
                                                next_line = line_no
                                        elif next_line is None:
                                            next_line = line_no
                                    pending.clear()
                                    line_no += 1
                        if size and (lines < line_no and pending):
                            lines = line_no
                            if used + len(pending) <= self.output_bytes - 1024:
                                item = {"line": line_no, "text": pending.decode("utf-8", errors="replace")}
                                if (
                                    used + len(json.dumps(item, ensure_ascii=False).encode())
                                    <= self.output_bytes - 1024
                                ):
                                    selected.append(item)
                                elif next_line is None:
                                    next_line = line_no
                            elif next_line is None:
                                next_line = line_no
                        # A last line outside the selected range still contributes totalLines.
                        if size and lines < line_no:
                            stream.seek(-1, os.SEEK_END)
                            if stream.read(1) != b"\n":
                                lines = line_no
                        sha = digest.hexdigest()
                ledger = self._ledger()
                ledger["reads"].setdefault(self.actor, {})[virtual] = sha
                self._save(ledger)
                next_line = next_line or (end_line + 1 if lines > end_line else None)
                return {
                    "ok": True,
                    "path": virtual,
                    "sha256": sha,
                    "size": size,
                    "totalLines": lines,
                    "lines": selected,
                    "truncated": next_line is not None,
                    "nextLine": next_line,
                }
            except FileNotFoundError:
                raise HarnessError("FILE_NOT_FOUND", "文件或父目录不存在。") from None
            except OSError:
                raise HarnessError("INVALID_PATH", "文件类型或路径不可访问。") from None

    def write_file(
        self,
        path: str,
        content: str,
        expected_hash: str | None = None,
        create_new: bool = False,
        *,
        execution_id: str | None = None,
    ) -> dict:
        raw = content.encode("utf-8")
        if len(raw) > 262144:
            raise HarnessError("OUTPUT_LIMIT", "单文件最多写入 256 KiB。")
        root, rel, virtual = self._parts(path, write=True)
        fingerprint = _hash(json.dumps([virtual, _hash(raw), expected_hash, create_new]).encode())
        with self.lock:
            ledger = self._ledger()
            if execution_id and execution_id in ledger["executions"]:
                previous = ledger["executions"][execution_id]
                if previous["fingerprint"] != fingerprint:
                    raise HarnessError("EXECUTION_CONFLICT", "同一工具执行标识的参数发生变化。")
                if previous.get("result"):
                    return previous["result"]
                # Reconcile a process crash between the filesystem mutation and receipt.
                try:
                    with self._parent(root, rel) as (parent_fd, name):
                        with os.fdopen(self._open(name, os.O_RDONLY, parent_fd), "rb") as stream:
                            observed = hashlib.file_digest(stream, "sha256").hexdigest()
                    if observed == _hash(raw):
                        result = {
                            "ok": True,
                            "path": virtual,
                            "sha256": observed,
                            "size": len(raw),
                            "truncated": False,
                        }
                        previous["result"] = result
                        ledger["reads"].get(self.actor, {}).pop(virtual, None)
                        self._save(ledger)
                        return result
                    if create_new or observed != expected_hash:
                        raise HarnessError(
                            "EXECUTION_UNCERTAIN", "中断工具的文件状态不明，禁止自动重复写入。"
                        )
                except FileNotFoundError:
                    if not create_new:
                        raise HarnessError(
                            "EXECUTION_UNCERTAIN", "中断后原文件丢失，禁止自动重复写入。"
                        ) from None
            try:
                with self._parent(root, rel) as (parent_fd, name):
                    if execution_id:
                        ledger["executions"][execution_id] = {"fingerprint": fingerprint, "result": None}
                        self._save(ledger)
                    if create_new:
                        try:
                            fd = self._open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, parent_fd)
                        except FileExistsError:
                            raise HarnessError(
                                "FILE_ALREADY_EXISTS", "文件已存在，覆盖前请先读取。"
                            ) from None
                        with os.fdopen(fd, "wb") as stream:
                            stream.write(raw)
                            stream.flush()
                            os.fsync(stream.fileno())
                    else:
                        read_hash = ledger["reads"].get(self.actor, {}).get(virtual)
                        if not read_hash or expected_hash != read_hash:
                            raise HarnessError(
                                "READ_REQUIRED", "覆盖前必须由当前 Agent 读取文件并传入读取哈希。"
                            )
                        with os.fdopen(self._open(name, os.O_RDONLY, parent_fd), "rb") as stream:
                            digest = hashlib.file_digest(stream, "sha256").hexdigest()
                        if digest != expected_hash:
                            raise HarnessError("FILE_CHANGED", "文件已发生变化，请重新读取后再写入。")
                        temp_name = ".cas-" + next(tempfile._get_candidate_names())
                        if parent_fd is None:
                            temp_name = str(Path(name).parent / temp_name)
                        try:
                            with os.fdopen(
                                self._open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, parent_fd), "wb"
                            ) as stream:
                                stream.write(raw)
                                stream.flush()
                                os.fsync(stream.fileno())
                            os.replace(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                        finally:
                            try:
                                os.unlink(temp_name, dir_fd=parent_fd)
                            except FileNotFoundError:
                                pass
                    result = {
                        "ok": True,
                        "path": virtual,
                        "sha256": _hash(raw),
                        "size": len(raw),
                        "truncated": False,
                    }
                    # A successful write is not an implicit read: another overwrite needs read_file.
                    ledger["reads"].get(self.actor, {}).pop(virtual, None)
                    if execution_id:
                        ledger["executions"][execution_id] = {"fingerprint": fingerprint, "result": result}
                    self._save(ledger)
                    return result
            except FileNotFoundError:
                raise HarnessError("FILE_NOT_FOUND", "文件或父目录不存在。") from None
            except OSError:
                raise HarnessError("INVALID_PATH", "文件类型或路径不可访问。") from None

    def list_dir(self, path: str = "/workspace", offset: int = 0, limit: int = 50) -> dict:
        root, rel, virtual = self._parts(path)
        if offset < 0 or limit < 1:
            raise HarnessError("INVALID_RANGE", "分页参数无效。")
        entries, used, directory_fd = [], 512, None
        try:
            if os.name == "posix":
                directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                for part in rel:
                    child_fd = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd
                    )
                    os.close(directory_fd)
                    directory_fd = child_fd
                directory = directory_fd
            else:
                directory = root.joinpath(*rel)
            with os.scandir(directory) as scan:
                names = sorted(scan, key=lambda entry: entry.name)
                cursor = offset
                for child in names[offset : offset + min(limit, 200)]:
                    info = child.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
                        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024
                    ):
                        cursor += 1
                        continue
                    item = {
                        "name": child.name,
                        "path": virtual + "/" + child.name,
                        "type": "directory" if stat.S_ISDIR(info.st_mode) else "file",
                    }
                    used += len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
                    if used > self.output_bytes:
                        break
                    entries.append(item)
                    cursor += 1
            return {
                "ok": True,
                "entries": entries,
                "truncated": cursor < len(names),
                "nextOffset": cursor if cursor < len(names) else None,
            }
        except FileNotFoundError:
            raise HarnessError("FILE_NOT_FOUND", "目录不存在。") from None
        except OSError:
            raise HarnessError("INVALID_PATH", "目录类型或路径不可访问。") from None
        finally:
            if directory_fd is not None:
                os.close(directory_fd)

    def search_content(self, query: str, path: str = "/workspace", limit: int = 20) -> dict:
        if not query or len(query) > 500:
            raise HarnessError("INVALID_QUERY", "搜索词须为 1–500 字。")
        root, rel, virtual = self._parts(path)
        target = root.joinpath(*rel)
        if not target.exists():
            raise HarnessError("FILE_NOT_FOUND", "搜索目录不存在。")
        matches, used, count, truncated = [], 512, 0, False
        started = time.monotonic()
        for directory, dirs, files in os.walk(target, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not Path(directory, d).is_symlink())
            for filename in sorted(files):
                count += 1
                if count > 200 or time.monotonic() - started > 5:
                    truncated = True
                    break
                physical = Path(directory, filename)
                vpath = virtual + "/" + physical.relative_to(target).as_posix()
                try:
                    _, f_rel, _ = self._parts(vpath)
                    with self._parent(root, f_rel) as (parent_fd, name):
                        with os.fdopen(self._open(name, os.O_RDONLY, parent_fd), "rb") as stream:
                            for line_no in range(1, 20001):
                                line = stream.readline(65536)
                                if not line:
                                    break
                                text = line.decode("utf-8", errors="replace")
                                if query.casefold() in text.casefold():
                                    position = text.casefold().find(query.casefold())
                                    item = {
                                        "path": vpath,
                                        "line": line_no,
                                        "text": text[
                                            max(0, position - 80) : position + len(query) + 200
                                        ].strip(),
                                    }
                                    used += len(json.dumps(item, ensure_ascii=False).encode())
                                    if len(matches) >= min(limit, 50) or used > self.output_bytes:
                                        truncated = True
                                        break
                                    matches.append(item)
                except (HarnessError, OSError):
                    continue
                if truncated:
                    break
            if truncated:
                break
        return {
            "ok": True,
            "matches": matches,
            "scannedFiles": min(count, 200),
            "truncated": truncated,
            "continuation": "请缩小搜索目录或关键词。" if truncated else None,
        }
