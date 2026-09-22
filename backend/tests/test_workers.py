"""Worker invariants on real MySQL; only this test's own records are consumed.

HTTP fixtures and the broker sender in unit checks are explicitly synthetic.
The live ingestion and Linux/Celery checks are separate integration evidence.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, timedelta
from threading import Event
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from test_api import verified_config

from zhigenews import workers
from zhigenews.application import next_slot
from zhigenews.contract import schema, validate
from zhigenews.db import Brief, Delivery, Outbox, Resource, Run, User, iso, transaction, utcnow
from zhigenews.ingestion import fetch_source

pytestmark = pytest.mark.mysql
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Synthetic worker feed</title>
<link>https://example.test/</link><description>Only a fixture</description>
<item><guid>item-1</guid><title>Synthetic AI item</title><link>https://example.test/ai</link></item>
</channel></rss>"""


@pytest.fixture
def sandbox(api_sandbox, tmp_path, monkeypatch):
    verified_config(api_sandbox, monkeypatch)
    monkeypatch.setattr(workers, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    yield api_sandbox
    with transaction() as session:
        for row in session.scalars(select(Resource).where(Resource.kind.in_(("snapshot", "source_fetch")))):
            if row.data.get("source_id") in api_sandbox.resources:
                api_sandbox.resources.add(row.id)


def source_record(sandbox, suffix="_source", *, interval=600, due=None):
    ident = sandbox.resource(sandbox.prefix + suffix)
    data = {
        "id": ident,
        "name": "Synthetic worker feed",
        "kind": "rss",
        "sourceId": "",
        "url": "https://example.test/feed.xml",
        "interval": interval,
        "status": "unverified",
        "lastSuccess": "",
        "nextFetch": iso(due or utcnow()),
        "lastChanged": "",
        "items": 0,
        "error": "",
        "snapshotId": None,
        "snapshotFetchedAt": None,
        "lastFetchedAt": None,
        "cacheAgeSeconds": None,
        "stale": True,
    }
    with transaction() as session:
        session.add(Resource(id=ident, kind="source", data=data, due_at=due or utcnow()))
    return ident


def collector(source, storage, **kwargs):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=RSS, headers={"etag": '"synthetic"'})
        )
    ) as client:
        return fetch_source(source, storage, client=client, jitter_ratio=0, **kwargs)


def configured_user(sandbox, suffix="_user", *, status="active", onboarding=True, due=None):
    ident = sandbox.prefix + suffix
    sandbox.users.add(ident)
    with transaction() as session:
        session.add(
            User(
                id=ident,
                name="Synthetic scheduled reader",
                role="anonymous",
                status=status,
                onboarding=onboarding,
                next_run_at=due or utcnow(),
                preference={"version": 1, "role": "", "topics": ["AI"], "keywords": []},
            )
        )
    return ident


def pending_brief(sandbox, suffix="_publication", *, generation="completed", published=False):
    user_id = configured_user(sandbox, suffix + "_user", due=utcnow() + timedelta(days=1))
    run_id, brief_id, delivery_id = (
        sandbox.prefix + suffix + ending for ending in ("_run", "_brief", "_del")
    )
    sandbox.resource(delivery_id)  # Include delivery-targeted outbox rows in scoped cleanup.
    with transaction() as session:
        session.add(
            Run(
                id=run_id,
                user_id=user_id,
                business_key=run_id,
                status="running",
                percent=95,
                preferences={},
                config={},
                private={"outputBriefId": brief_id},
            )
        )
        session.flush()
        session.add(
            Brief(
                id=brief_id,
                user_id=user_id,
                run_id=run_id,
                date="2026-09-19",
                version=1,
                published=published,
                data={
                    "id": brief_id,
                    "title": "Synthetic worker brief",
                    "date": "2026-09-19",
                    "version": 1,
                    "summary": "Synthetic only",
                    "items": [],
                    "generationStatus": generation,
                    "deliveryStatus": "pending",
                    "generatedAt": iso(utcnow()),
                    "missingSources": [],
                },
            )
        )
        session.flush()
        session.add(Delivery(id=delivery_id, user_id=user_id, brief_id=brief_id, status="pending"))
    return user_id, run_id, brief_id, delivery_id


def test_source_collection_persists_snapshot_attempt_and_public_contract(sandbox):
    ident = source_record(sandbox)
    result = workers.collect_source(ident, collector=collector)
    assert result["status"] == "healthy"
    with transaction() as session:
        row = session.get(Resource, ident)
        validate(schema("Source"), row.data, output=True)
        assert row.data["items"] == 1 and row.private["state"]["etag"] == '"synthetic"'
        snapshot = session.get(Resource, result["snapshot_id"])
        assert snapshot.kind == "snapshot" and len(snapshot.private["items"]) == 1
        assert snapshot.private["items"][0]["published_at"] is None
        assert row.lease_token is None and row.lease_until is None
        assert row.due_at > utcnow()
        assert session.get(Resource, "fetch_" + row.private["last_attempt"]["id"])


def test_duplicate_source_task_does_not_fetch_before_its_interval(sandbox):
    ident = source_record(sandbox)
    workers.collect_source(ident, collector=collector)
    calls = []

    def unexpected(*args, **kwargs):
        calls.append(True)
        return collector(*args, **kwargs)

    assert workers.collect_source(ident, collector=unexpected)["status"] == "deferred"
    assert calls == []


def test_source_worker_exception_releases_lease_and_persists_next_retry(sandbox):
    ident = source_record(sandbox)

    def disk_failure(*args, **kwargs):
        raise OSError("synthetic storage failure")

    with pytest.raises(OSError, match="synthetic storage failure"):
        workers.collect_source(ident, collector=disk_failure)
    with transaction() as session:
        row = session.get(Resource, ident)
        assert row.data["status"] == "failed" and row.data["snapshotId"] is None
        assert row.lease_token is None and row.lease_until is None
        assert row.due_at > utcnow()
        assert abs((workers._date(row.data["nextFetch"]) - row.due_at).total_seconds()) < 1


def test_concurrent_source_tasks_have_one_network_owner(sandbox):
    ident = source_record(sandbox)
    entered, release = Event(), Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return collector(*args, **kwargs)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(workers.collect_source, ident, collector=blocked)
        assert entered.wait(10)
        duplicate = workers.collect_source(ident, collector=collector)
        release.set()
        result = first.result(timeout=10)
    assert duplicate["status"] == "busy" and result["status"] == "healthy"


def test_stale_lease_cannot_publish_snapshot_or_overwrite_new_owner(sandbox, tmp_path):
    ident = source_record(sandbox)

    def superseded(*args, **kwargs):
        with transaction() as session:
            row = session.get(Resource, ident)
            row.lease_token = "synthetic-new-owner"
        return collector(*args, **kwargs)

    result = workers.collect_source(ident, collector=superseded)
    assert result["status"] == "superseded"
    with transaction() as session:
        row = session.get(Resource, ident)
        assert row.lease_token == "synthetic-new-owner"
        assert row.data["snapshotId"] is None
    assert not list(tmp_path.rglob("latest.json"))
    assert not list(tmp_path.rglob("index.json"))


def test_due_sources_keep_independent_intervals_and_survive_scheduler_restart(sandbox):
    now = utcnow()
    first, second = (
        source_record(sandbox, "_first", interval=120),
        source_record(sandbox, "_second", interval=3600),
    )
    queued = workers.schedule_due(source_ids=[first, second], user_ids=[], now=now + timedelta(seconds=1))
    assert set(queued["sources"]) == {first, second}
    assert (
        workers.schedule_due(source_ids=[first, second], user_ids=[], now=now + timedelta(seconds=2))[
            "sources"
        ]
        == []
    )
    workers.collect_source(first, collector=collector)
    workers.collect_source(second, collector=collector)
    with transaction() as session:
        one, two = session.get(Resource, first), session.get(Resource, second)
        assert abs((two.due_at - one.due_at).total_seconds() - 3480) < 3
        assert one.data["interval"] == 120 and two.data["interval"] == 3600


def test_daily_scheduler_is_atomic_idempotent_and_excludes_ineligible_accounts(sandbox):
    now = utcnow().replace(microsecond=0)
    eligible = configured_user(sandbox, "_eligible", due=now)
    blocked = configured_user(sandbox, "_blocked", status="blocked", due=now)
    unconfigured = configured_user(sandbox, "_empty", onboarding=False, due=now)
    ids = [eligible, blocked, unconfigured]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: workers.schedule_due(source_ids=[], user_ids=ids, now=now + timedelta(seconds=1)),
                range(2),
            )
        )
    assert sum(len(result["runs"]) for result in results) == 1
    with transaction() as session:
        runs = list(session.scalars(select(Run).where(Run.user_id.in_(ids))))
        assert len(runs) == 1
        assert runs[0].business_key == f"daily:{eligible}:{iso(now)}"
        assert session.get(User, eligible).next_run_at > now
        assert session.get(User, blocked).next_run_at is None
        assert session.get(User, unconfigured).next_run_at is None
        assert (
            session.scalar(select(func.count()).select_from(Outbox).where(Outbox.target_id == runs[0].id))
            == 1
        )


def test_scheduler_skips_yesterdays_slots_and_uses_shanghai_time(sandbox):
    now = utcnow()
    ident = configured_user(sandbox, due=now - timedelta(days=1))
    assert workers.schedule_due(source_ids=[], user_ids=[ident], now=now)["runs"] == []
    with transaction() as session:
        assert session.get(User, ident).next_run_at == next_slot("08:00", now)
    assert next_slot("08:00", _dt("2026-09-18T23:59:00+00:00")) == _dt("2026-09-19T00:00:00+00:00")
    assert next_slot("08:00", _dt("2026-09-19T00:00:00+00:00")) == _dt("2026-09-20T00:00:00+00:00")


def _dt(value):
    from datetime import datetime

    return datetime.fromisoformat(value).astimezone(UTC).replace(tzinfo=None)


def test_outbox_ack_failure_leaves_command_and_success_marks_only_own_record(sandbox):
    target = source_record(sandbox)
    ident = sandbox.prefix + "_outbox"
    with transaction() as session:
        session.add(Outbox(id=ident, kind="source", target_id=target))

    def failed_sender(*args, **kwargs):
        raise ConnectionError("synthetic broker unavailable")

    result = workers.dispatch_outbox(outbox_ids=[ident], send=failed_sender)
    assert result["failed"] == [ident]
    with transaction() as session:
        assert session.get(Outbox, ident).sent_at is None
    calls = []
    result = workers.dispatch_outbox(
        outbox_ids=[ident], send=lambda *args, **kwargs: calls.append((args, kwargs))
    )
    assert result["sent"] == [ident]
    assert calls == [(("zhigenews.source",), {"args": [target], "task_id": ident})]
    assert (
        workers.dispatch_outbox(
            outbox_ids=[ident], send=lambda *args, **kwargs: pytest.fail("duplicate send")
        )["sent"]
        == []
    )


def test_publication_is_atomic_idempotent_and_sets_progress_after_publish(sandbox):
    user_id, run_id, brief_id, delivery_id = pending_brief(sandbox, generation="partial")
    with transaction() as session:
        assert not session.get(Brief, brief_id).published
        assert session.get(Run, run_id).percent == 95
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: workers.publish_delivery(delivery_id), range(2)))
    with transaction() as session:
        run, brief, delivery = (
            session.get(Run, run_id),
            session.get(Brief, brief_id),
            session.get(Delivery, delivery_id),
        )
        assert brief.published and brief.data["deliveryStatus"] == "submitted"
        assert delivery.status == "submitted" and delivery.attempts == 1
        assert run.status == "partial" and run.percent == 100 and run.remaining_seconds == 0
        assert run.brief_id == brief_id and run.private["outputBriefId"] == brief_id
        assert session.scalar(
            select(Resource).where(Resource.kind == "memory", Resource.owner_id == user_id)
        ) is None


def test_publication_failure_and_explicit_retry_reuse_exact_brief(sandbox):
    _, run_id, brief_id, delivery_id = pending_brief(sandbox, generation="running")
    assert workers.publish_delivery(delivery_id)["status"] == "failed"
    assert workers.publish_delivery(delivery_id)["attempts"] == 1
    with transaction() as session:
        run, brief, delivery = (
            session.get(Run, run_id),
            session.get(Brief, brief_id),
            session.get(Delivery, delivery_id),
        )
        assert not brief.published and run.status == "failed" and run.percent == 95
        assert run.error
        brief.data = {**brief.data, "generationStatus": "completed"}
        delivery.status = "pending"
    assert workers.publish_delivery(delivery_id)["attempts"] == 2
    with transaction() as session:
        assert session.get(Brief, brief_id).published
        assert session.scalar(select(func.count()).select_from(Brief).where(Brief.run_id == run_id)) == 1


def test_blocked_or_cancelled_publication_never_reports_completion(sandbox):
    user_id, run_id, brief_id, delivery_id = pending_brief(sandbox)
    with transaction() as session:
        session.get(User, user_id).status = "blocked"
    assert workers.publish_delivery(delivery_id)["status"] == "disabled"
    with transaction() as session:
        assert not session.get(Brief, brief_id).published
        assert session.get(Run, run_id).percent == 95


def test_recovery_routes_existing_brief_to_delivery_without_rerunning_model(sandbox):
    _, run_id, _, delivery_id = pending_brief(sandbox)
    recovered = workers.recover_runs(run_ids=[run_id])
    assert recovered == [{"kind": "delivery", "id": delivery_id}]
    assert workers.recover_runs(run_ids=[run_id]) == []
    with transaction() as session:
        commands = list(session.scalars(select(Outbox).where(Outbox.target_id.in_([run_id, delivery_id]))))
        assert len(commands) == 1 and commands[0].kind == "delivery"


@pytest.mark.parametrize("lease_seconds", [None, -30, 90])
def test_recovery_finishes_abandoned_cancellation_before_requeue(sandbox, lease_seconds):
    _, run_id, brief_id, delivery_id = pending_brief(sandbox)
    now = utcnow()
    with transaction() as session:
        run = session.get(Run, run_id)
        run.status, run.cancel_requested = "cancelling", True
        # Cancellation must not wait for the recovery requeue throttle either.
        run.private = {**run.private, "lastRecoveryQueuedAt": iso(now)}
        if lease_seconds is not None:
            run.lease_token = "synthetic-abandoned-worker"
            run.lease_until = now + timedelta(seconds=lease_seconds)
    assert workers.recover_runs(run_ids=[run_id], now=now) == []
    with transaction() as session:
        run = session.get(Run, run_id)
        assert run.status == "cancelled" and run.lease_token is None and run.lease_until is None
        assert session.scalar(select(Outbox).where(Outbox.target_id.in_([run_id, delivery_id]))) is None
    # Even a delayed publication command must respect the cancellation flag.
    assert workers.publish_delivery(delivery_id)["status"] == "disabled"
    with transaction() as session:
        assert not session.get(Brief, brief_id).published
        assert session.get(Run, run_id).status == "cancelled"
