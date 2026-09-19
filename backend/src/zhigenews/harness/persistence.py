"""MySQL 8 checkpoint adapter for resumable agent runs."""

from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import unquote, urlsplit

import pymysql
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

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
    checkpoint_conn = _connection(database_url)
    try:
        saver = PyMySQLSaver(checkpoint_conn)
        if setup:
            saver.setup()
        yield saver
    finally:
        checkpoint_conn.close()
