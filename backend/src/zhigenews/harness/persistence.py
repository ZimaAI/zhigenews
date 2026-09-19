"""MySQL 8 checkpoint and Store adapters, scoped to the server's user identity."""

from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import unquote, urlsplit

import pymysql
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from langgraph.store.mysql.pymysql import PyMySQLStore

from .errors import HarnessError


def _connection(database_url: str):
    url = urlsplit(database_url)
    if url.scheme not in ("mysql", "mysql+pymysql", "mysql+aiomysql"):
        raise HarnessError("MYSQL_REQUIRED", "Harness 持久化要求 MySQL 数据库。")
    return pymysql.connect(
        host=url.hostname or "localhost",
        port=url.port or 3306,
        user=unquote(url.username or ""),
        password=unquote(url.password or ""),
        database=url.path.lstrip("/"),
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=10,
    )


@contextmanager
def mysql_persistence(database_url: str, *, setup: bool = False):
    checkpoint_conn, store_conn = _connection(database_url), _connection(database_url)
    try:
        saver, store = PyMySQLSaver(checkpoint_conn), PyMySQLStore(store_conn)
        if setup:
            saver.setup()
            store.setup()
        yield saver, store
    finally:
        checkpoint_conn.close()
        store_conn.close()


class UserMemory:
    """Namespace is injected by the worker, never accepted from a tool argument."""

    def __init__(self, store, user_id: str):
        self.store, self.namespace = store, ("users", user_id, "memory")

    def list(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return [
            {"id": item.key, **item.value, "updatedAt": item.updated_at.isoformat()}
            for item in self.store.search(self.namespace, limit=min(limit, 100), offset=offset)
        ]

    def iter_all(self):
        """Snapshot all pages before yielding so deletion cannot skip later rows."""
        items, offset = [], 0
        while page := self.list(limit=100, offset=offset):
            items.extend(page)
            offset += len(page)
            if len(page) < 100:
                break
        yield from items

    def put(self, key: str, value: dict, *, source: str) -> None:
        if source not in ("explicit_preference", "user_feedback", "published_brief"):
            raise HarnessError("INVALID_MEMORY_SOURCE", "网络文本不能写为用户事实。")
        self.store.put(self.namespace, key, {**value, "source": source})

    def delete(self, key: str) -> None:
        self.store.delete(self.namespace, key)
