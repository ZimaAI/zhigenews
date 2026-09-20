"""Real-MySQL API fixtures, scoped to records created by each test only."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select

from zhigenews.db import (
    Brief,
    Bucket,
    Delivery,
    Idempotency,
    Outbox,
    PreferenceRevision,
    Resource,
    Run,
    RunEvent,
    SessionToken,
    SourceDeletionItem,
    SourceDeletionJob,
    User,
    transaction,
)
from zhigenews.security import password_hash


@pytest.fixture(autouse=True)
def disable_external_tracing(monkeypatch):
    """Synthetic regression runs must not be exported using developer credentials."""
    from zhigenews import tracing

    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(tracing, "get_tracing_client", lambda: None)


@dataclass
class ApiSandbox:
    app: object
    prefix: str = field(default_factory=lambda: "api_test_" + uuid4().hex[:14])
    users: set[str] = field(default_factory=set)
    resources: set[str] = field(default_factory=set)
    clients: list[TestClient] = field(default_factory=list)
    admin_credentials: dict[str, str] = field(default_factory=dict)
    next_peer: int = 1

    def client(self, *, headers=True) -> TestClient:
        peer = int(self.prefix[-6:], 16)
        address = f"198.18.{peer % 254}.{self.next_peer}"
        self.next_peer += 1
        client = TestClient(
            self.app, client=(address, 41000 + self.next_peer),
            headers={"X-Zhige-Request": "1", "Origin": "http://127.0.0.1:5173"} if headers else {},
        )
        self.clients.append(client)
        return client

    def anonymous(self) -> TestClient:
        client = self.client()
        response = client.post("/api/v1/auth/anonymous")
        assert response.status_code == 200, response.text
        self.users.add(response.json()["userId"])
        return client

    def admin(self) -> TestClient:
        user_id = self.prefix + "_admin"
        email = self.prefix + "@example.test"
        password = "Synthetic-only-" + uuid4().hex
        self.admin_credentials = {"email": email, "password": password}
        with transaction() as session:
            session.add(User(id=user_id, name="Synthetic API administrator", role="admin", email=email,
                             password_hash=password_hash(password)))
        self.users.add(user_id)
        client = self.client()
        response = client.post("/api/v1/admin/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return client

    def resource(self, resource_id: str) -> str:
        self.resources.add(resource_id)
        return resource_id

    def cleanup(self):
        for client in self.clients:
            client.close()
        with transaction() as session:
            run_ids = list(session.scalars(select(Run.id).where(Run.user_id.in_(self.users))))
            brief_ids = list(session.scalars(select(Brief.id).where(Brief.user_id.in_(self.users))))
            delivery_ids = list(session.scalars(select(Delivery.id).where(Delivery.user_id.in_(self.users))))
            owned_ids = list(session.scalars(select(Resource.id).where(Resource.owner_id.in_(self.users))))
            resource_ids = self.resources | set(owned_ids)
            deletion_ids = list(session.scalars(select(SourceDeletionItem.job_id).where(SourceDeletionItem.source_id.in_(resource_ids))))
            # Administrative audit records identify the test actor in private metadata.
            for record in session.scalars(select(Resource).where(Resource.kind == "abuse")):
                if record.data.get("accountId") in self.users or record.private.get("actor") in self.users:
                    resource_ids.add(record.id)
            target_ids = set(run_ids) | set(brief_ids) | set(delivery_ids) | resource_ids | set(deletion_ids)
            for record in session.scalars(select(Idempotency)):
                if record.response.get("id") in target_ids or record.response.get("evaluationId") in target_ids:
                    session.delete(record)
            session.execute(delete(Outbox).where(Outbox.target_id.in_(target_ids)))
            session.execute(delete(SourceDeletionItem).where(SourceDeletionItem.job_id.in_(deletion_ids)))
            session.execute(delete(SourceDeletionJob).where(SourceDeletionJob.id.in_(deletion_ids)))
            session.execute(delete(Delivery).where(Delivery.user_id.in_(self.users)))
            session.execute(delete(Brief).where(Brief.user_id.in_(self.users)))
            session.execute(delete(RunEvent).where(RunEvent.run_id.in_(run_ids)))
            session.execute(delete(Run).where(Run.user_id.in_(self.users)))
            session.execute(delete(Resource).where(Resource.id.in_(resource_ids)))
            session.execute(delete(PreferenceRevision).where(PreferenceRevision.user_id.in_(self.users)))
            session.execute(delete(SessionToken).where(SessionToken.user_id.in_(self.users)))
            if self.users:
                patterns = [Bucket.key.like(prefix + user_id + ":%") for user_id in self.users for prefix in ("request:", "generate:")]
                session.execute(delete(Bucket).where(or_(*patterns)))
            session.execute(delete(User).where(User.id.in_(self.users)))


@pytest.fixture
def api_sandbox():
    from zhigenews.gateway import app

    fixture = ApiSandbox(app)
    try:
        yield fixture
    finally:
        fixture.cleanup()
