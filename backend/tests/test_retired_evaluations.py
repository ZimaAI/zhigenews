"""Retired HTTP routes and outbox isolation, without external services."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from zhigenews import workers
from zhigenews.contract import CONTRACT
from zhigenews.db import Outbox, utcnow
from zhigenews.gateway import app


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/admin/evaluations"),
        ("POST", "/admin/evaluations"),
        ("GET", "/admin/evaluations/legacy"),
        ("GET", "/admin/eval-cases"),
        ("POST", "/admin/eval-cases"),
        ("PUT", "/admin/eval-cases/legacy"),
    ],
)
def test_retired_routes_return_not_found(method, path):
    with TestClient(app) as client:
        response = client.request(method, "/api/v1" + path)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert not any(path.startswith(("/admin/evaluations", "/admin/eval-cases")) for path in CONTRACT["paths"])


def test_retired_outbox_rows_do_not_block_active_work(monkeypatch):
    engine = create_engine("sqlite://")
    Outbox.__table__.create(engine)
    sessions = sessionmaker(engine)
    monkeypatch.setattr(workers, "transaction", sessions.begin)
    now = utcnow()
    try:
        with sessions.begin() as session:
            session.add_all([
                Outbox(id="retired", kind="evaluation", target_id="old", created_at=now - timedelta(days=1)),
                Outbox(id="active", kind="run", target_id="current", created_at=now),
            ])
        calls = []
        result = workers.dispatch_outbox(limit=1, send=lambda *args, **kwargs: calls.append((args, kwargs)))
        assert result == {"sent": ["active"], "failed": []}
        assert calls == [(("zhigenews.run",), {"args": ["current"], "task_id": "active"})]
        with sessions.begin() as session:
            assert session.get(Outbox, "retired").sent_at is None
            assert session.get(Outbox, "active").sent_at is not None
        assert "zhigenews.evaluation" not in workers.celery_app.tasks
    finally:
        engine.dispose()
