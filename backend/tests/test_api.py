"""Backend acceptance against the real MySQL gateway; no mocked persistence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, timedelta

import pytest
from sqlalchemy import select

from zhigenews.application import CN, next_slot
from zhigenews.contract import CONTRACT, schema, validate
from zhigenews.db import (
    Brief,
    Delivery,
    PreferenceRevision,
    Resource,
    Run,
    SessionToken,
    User,
    iso,
    transaction,
    utcnow,
)
from zhigenews.security import decrypt, digest, encrypt, locked_bucket, policy
from zhigenews.settings import Settings

pytestmark = pytest.mark.mysql
BASE = "/api/v1"


def assert_dto(response, name, status=200):
    assert response.status_code == status, response.text
    payload = response.json()
    validate(schema(name), payload, output=True)
    return payload


def preferences(client, **changes):
    value = {"version": 0, "role": "Synthetic API test reader", "topics": ["Agent 工程"], "keywords": ["Agent"]}
    value.update(changes)
    return client.put(BASE + "/me/preferences", json=value)


def verified_config(sandbox, monkeypatch, **overrides):
    """Use synthetic file settings; these API tests never execute model workers."""
    from zhigenews import runtime_config

    values = dict(
        openai_model="synthetic-test-model",
        openai_base_url="https://fixture.invalid/v1",
        openai_api_key="synthetic-model-secret-" + sandbox.prefix,
        summary_openai_model="",
        summary_openai_base_url="",
        summary_openai_api_key="",
    )
    values.update(overrides)
    configured = Settings(_env_file=None, **values)
    monkeypatch.setattr(runtime_config, "get_settings", lambda: configured)
    return runtime_config.agent_config()


def test_anonymous_cookie_restores_identity_and_persists_only_hash(api_sandbox):
    client = api_sandbox.client()
    response = client.post(BASE + "/auth/anonymous")
    data = assert_dto(response, "Session")
    api_sandbox.users.add(data["userId"])
    assert data["kind"] == "anonymous" and data["onboardingCompleted"] is False
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert "token" not in data
    token = client.cookies.get("zg_session")
    with transaction() as session:
        record = session.get(SessionToken, digest(token))
        assert record is not None and record.user_id == data["userId"]
        assert record.token_hash != token
    assert assert_dto(client.post(BASE + "/auth/anonymous"), "Session") == data
    assert assert_dto(client.get(BASE + "/auth/session"), "Session") == data


def test_lost_cookie_is_a_new_identity_and_admin_cookie_is_independent(api_sandbox):
    user = api_sandbox.anonymous()
    old = user.get(BASE + "/auth/session").json()["userId"]
    user.cookies.clear()
    assert user.get(BASE + "/auth/session").status_code == 401
    new = assert_dto(user.post(BASE + "/auth/anonymous"), "Session")
    api_sandbox.users.add(new["userId"])
    assert new["userId"] != old
    assert user.get(BASE + "/admin/overview").status_code == 403
    admin = api_sandbox.admin()
    assert_dto(admin.get(BASE + "/admin/auth/session"), "AdminSession")
    assert admin.get(BASE + "/auth/session").status_code == 401
    assert admin.delete(BASE + "/admin/auth/session").status_code == 204
    assert admin.get(BASE + "/admin/auth/session").status_code == 401


def test_csrf_rejects_foreign_origin_and_missing_required_header(api_sandbox):
    client = api_sandbox.anonymous()
    assert preferences(client).status_code == 200
    payload = {"version": 1, "role": "", "topics": ["AI"], "keywords": []}
    response = client.put(BASE + "/me/preferences", json=payload, headers={"Origin": "https://attacker.invalid"})
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_REJECTED"
    client.headers.pop("X-Zhige-Request")
    assert client.put(BASE + "/me/preferences", json=payload).status_code == 403
    assert client.get(BASE + "/me/preferences").json()["version"] == 1


def test_preferences_validation_atomic_onboarding_and_cas(api_sandbox):
    client = api_sandbox.anonymous()
    assert preferences(client, topics=[], keywords=[]).status_code == 400
    assert preferences(client, role="x" * 501).status_code == 400
    assert preferences(client, keywords=["x"] * 21).status_code == 400
    assert preferences(client, userId="other-user").status_code == 400
    assert client.get(BASE + "/auth/session").json()["onboardingCompleted"] is False
    saved = assert_dto(preferences(client), "Preferences")
    assert saved["version"] == 1
    assert client.get(BASE + "/auth/session").json()["onboardingCompleted"] is True
    assert preferences(client, version=0, topics=["stale"]).status_code == 409
    assert client.get(BASE + "/me/preferences").json() == saved
    user_id = client.get(BASE + "/auth/session").json()["userId"]
    with transaction() as session:
        revision = session.scalar(select(PreferenceRevision).where(PreferenceRevision.user_id == user_id))
        assert revision.version == 1 and revision.data == saved
        assert session.scalar(
            select(Resource).where(Resource.kind == "memory", Resource.owner_id == user_id)
        ) is None


def test_two_simultaneous_preference_writes_have_one_winner(api_sandbox):
    client = api_sandbox.anonymous()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda topic: preferences(client, topics=[topic]), ["Agent", "模型"]))
    assert sorted(response.status_code for response in results) == [200, 409]
    assert client.get(BASE + "/me/preferences").json()["version"] == 1


def test_delivery_settings_accept_only_time_and_do_not_generate(api_sandbox):
    client = api_sandbox.anonymous()
    assert_dto(client.get(BASE + "/me/delivery-settings"), "DeliverySettings")
    assert_dto(client.put(BASE + "/me/delivery-settings", json={"time": "09:15"}), "DeliverySettings")
    assert client.get(BASE + "/me/delivery-settings").json() == {"time": "09:15"}
    assert client.put(BASE + "/me/delivery-settings", json={"time": "24:00"}).status_code == 400
    assert client.put(BASE + "/me/delivery-settings", json={"time": "09:00", "timezone": "UTC"}).status_code == 400
    assert client.get(BASE + "/me/generations/current").json() is None


def test_long_term_memory_endpoints_are_removed(api_sandbox):
    client = api_sandbox.anonymous()
    assert client.get(BASE + "/me/memories").status_code == 404
    assert client.delete(BASE + "/me/memories/legacy-memory").status_code == 404
    assert not any(path.startswith("/me/memories") for path in CONTRACT["paths"])


def test_model_and_agent_configuration_endpoints_are_removed(api_sandbox):
    admin = api_sandbox.admin()
    for method, path in [
        ("get", "/admin/models"),
        ("post", "/admin/models"),
        ("put", "/admin/models/legacy-model"),
        ("put", "/admin/models/legacy-model/enabled"),
        ("post", "/admin/models/legacy-model/test"),
        ("delete", "/admin/models/legacy-model/secret"),
        ("get", "/admin/agent-configs"),
        ("post", "/admin/agent-configs"),
        ("put", "/admin/agent-configs/legacy-config"),
        ("post", "/admin/agent-configs/legacy-config/publish"),
    ]:
        response = admin.request(method, BASE + path, json={})
        assert response.status_code == 404, (method, path, response.text)
    assert not any(path.startswith(("/admin/models", "/admin/agent-configs")) for path in CONTRACT["paths"])


def test_generation_uses_file_models_and_code_constants_over_legacy_database_config(api_sandbox, monkeypatch):
    config = verified_config(api_sandbox, monkeypatch, openai_thinking_enabled=True)
    legacy_model = api_sandbox.resource(api_sandbox.prefix + "_legacy_model")
    legacy_config = api_sandbox.resource(api_sandbox.prefix + "_legacy_config")
    with transaction() as session:
        session.add(Resource(
            id=legacy_model, kind="model", secret=encrypt("synthetic-legacy-secret"),
            data={"id": legacy_model, "name": "Legacy model", "modelId": "legacy-model", "enabled": True, "verified": True},
        ))
        session.add(Resource(
            id=legacy_config, kind="config",
            data={**config, "id": legacy_config, "version": "v99999", "status": "published",
                  "modelId": legacy_model, "summaryModelId": legacy_model, "systemPrompt": "Legacy mutable prompt"},
        ))
    client, admin = api_sandbox.anonymous(), api_sandbox.admin()
    assert preferences(client).status_code == 200
    progress = assert_dto(client.post(
        BASE + "/me/briefs", json={"preferenceVersion": 1},
        headers={"Idempotency-Key": api_sandbox.prefix + "-snapshot"},
    ), "GenerationProgress", 202)
    with transaction() as session:
        run = session.get(Run, progress["id"])
        assert run.config == config
        frozen_models = run.private["models"]
        for snapshot in frozen_models.values():
            assert snapshot["data"]["modelId"] == "synthetic-test-model"
            assert snapshot["data"]["endpoint"] == "https://fixture.invalid/v1"
            assert snapshot["data"]["thinkingEnabled"] is True
            assert "apiKey" not in snapshot["data"]
            assert decrypt(snapshot["encryptedSecret"]) == "synthetic-model-secret-" + api_sandbox.prefix
            assert "synthetic-model-secret-" not in str(snapshot)
        encrypted_secrets = [snapshot["encryptedSecret"] for snapshot in frozen_models.values()]

    # Later file edits leave an accepted run's frozen dependencies intact.
    verified_config(api_sandbox, monkeypatch, openai_model="synthetic-later-model", openai_api_key="synthetic-later-key")
    public_run = assert_dto(admin.get(BASE + f"/admin/runs/{progress['id']}"), "AgentRun")
    assert public_run["configVersion"] == config["version"]
    for response in [public_run, client.get(BASE + f"/me/generations/{progress['id']}").json()]:
        assert config["systemPrompt"] not in str(response)
        assert "synthetic-model-secret-" not in str(response)
        assert all(secret not in str(response) for secret in encrypted_secrets)
    with transaction() as session:
        run = session.get(Run, progress["id"])
        assert run.config == config and run.private["models"] == frozen_models


@pytest.mark.parametrize("missing", ["openai_model", "openai_base_url", "openai_api_key"])
def test_missing_file_model_configuration_returns_503_without_creating_a_run(api_sandbox, monkeypatch, missing):
    verified_config(api_sandbox, monkeypatch, **{missing: ""})
    client = api_sandbox.anonymous()
    user_id = client.get(BASE + "/auth/session").json()["userId"]
    assert preferences(client).status_code == 200
    error = assert_dto(client.post(
        BASE + "/me/briefs", json={"preferenceVersion": 1},
        headers={"Idempotency-Key": api_sandbox.prefix + "-missing-config"},
    ), "Error", 503)
    assert error["code"] == "DEPENDENCY_UNAVAILABLE" and error["message"]
    assert "synthetic-model-secret-" not in str(error)
    with transaction() as session:
        assert not list(session.scalars(select(Run).where(Run.user_id == user_id)))


def test_generation_idempotency_current_recovery_and_cross_user_visibility(api_sandbox, monkeypatch):
    verified_config(api_sandbox, monkeypatch)
    client = api_sandbox.anonymous()
    other = api_sandbox.anonymous()
    assert preferences(client).status_code == 200
    headers = {"Idempotency-Key": api_sandbox.prefix + "-generation"}
    first = assert_dto(client.post(BASE + "/me/briefs", json={"preferenceVersion": 1}, headers=headers), "GenerationProgress", 202)
    again = assert_dto(client.post(BASE + "/me/briefs", json={"preferenceVersion": 1}, headers=headers), "GenerationProgress", 202)
    assert first["id"] == again["id"]
    current = assert_dto(client.get(BASE + "/me/generations/current"), "GenerationProgress")
    assert current["id"] == first["id"]
    assert set(current) == set(CONTRACT["components"]["schemas"]["GenerationProgress"]["properties"])
    assert other.get(BASE + f"/me/generations/{first['id']}").status_code == 404
    assert other.post(BASE + f"/me/generations/{first['id']}/cancel").status_code == 404
    failure = assert_dto(client.post(BASE + "/me/briefs", json={"preferenceVersion": 2}, headers=headers), "Error", 409)
    assert failure["code"] == "VERSION_CONFLICT"


def test_simultaneous_generation_replays_enqueue_only_one_run(api_sandbox, monkeypatch):
    verified_config(api_sandbox, monkeypatch)
    client = api_sandbox.anonymous()
    user_id = client.get(BASE + "/auth/session").json()["userId"]
    assert preferences(client).status_code == 200
    headers = {"Idempotency-Key": api_sandbox.prefix + "-concurrent"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(BASE + "/me/briefs", json={"preferenceVersion": 1}, headers=headers), range(2)))
    results = [assert_dto(response, "GenerationProgress", 202) for response in responses]
    assert results[0]["id"] == results[1]["id"]
    with transaction() as session:
        assert len(list(session.scalars(select(Run).where(Run.user_id == user_id)))) == 1


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize(
    ("status", "lease_seconds", "expected"),
    [
        ("queued", None, "cancelled"),
        ("cancelling", None, "cancelled"),
        ("running", -30, "cancelled"),
        ("running", 90, "cancelled"),
        ("completed", None, "completed"),
    ],
)
def test_cancel_generation_without_worker(api_sandbox, monkeypatch, admin, status, lease_seconds, expected):
    verified_config(api_sandbox, monkeypatch)
    reader = api_sandbox.anonymous()
    assert preferences(reader).status_code == 200
    created = assert_dto(
        reader.post(
            BASE + "/me/briefs", json={"preferenceVersion": 1},
            headers={"Idempotency-Key": api_sandbox.prefix + "-cancel"},
        ),
        "GenerationProgress", 202,
    )
    run_id = created["id"]
    with transaction() as session:
        run = session.get(Run, run_id)
        run.status = status
        run.cancel_requested = status == "cancelling"
        if lease_seconds is not None:
            run.lease_token = "synthetic-worker-lease"
            run.lease_until = utcnow() + timedelta(seconds=lease_seconds)
    client = api_sandbox.admin() if admin else reader
    path = BASE + ("/admin/runs/" if admin else "/me/generations/") + run_id + "/cancel"
    for _ in range(2):
        result = assert_dto(client.post(path), "AgentRun" if admin else "GenerationProgress", 202)
        assert result["status"] == expected
    assert reader.get(BASE + "/me/generations/current").json()["status"] == expected
    with transaction() as session:
        run = session.get(Run, run_id)
        assert run.cancel_requested == (status != "completed")
        if expected == "cancelled":
            assert run.lease_token is None and run.lease_until is None
            assert run.remaining_seconds is None
    if expected == "cancelled":
        # A command delivered after cancellation must never start the model.
        from zhigenews.execution import execute_run

        execute_run(run_id)
        with transaction() as session:
            assert session.get(Run, run_id).status == "cancelled"
            assert session.scalar(select(Brief).where(Brief.run_id == run_id)) is None


def saturate_request_bucket(user_id):
    minute = utcnow().replace(second=0, microsecond=0)
    with transaction() as session:
        # Also populate the next minute for a request crossing a minute boundary.
        for start in (minute, minute + timedelta(minutes=1)):
            bucket = locked_bucket(session, "request:" + user_id + ":" + start.isoformat(), start + timedelta(minutes=1))
            bucket.count = policy(session)["requestsPerMinute"]


def test_request_limit_returns_retry_after_and_records_real_risk(api_sandbox):
    client = api_sandbox.anonymous()
    user_id = client.get(BASE + "/auth/session").json()["userId"]
    saturate_request_bucket(user_id)
    response = client.get(BASE + "/me/preferences")
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert_dto(response, "Error", 429)
    with transaction() as session:
        assert session.get(User, user_id).rate_limit_hits == 1
        events = list(session.scalars(select(Resource).where(Resource.kind == "abuse")))
        assert any(event.data.get("accountId") == user_id and event.data["kind"] == "rate_limited" for event in events)


def test_existing_cookie_session_recovery_cannot_bypass_account_request_limit(api_sandbox):
    client = api_sandbox.anonymous()
    user_id = client.get(BASE + "/auth/session").json()["userId"]
    token = client.cookies.get("zg_session")
    saturate_request_bucket(user_id)
    response = client.post(BASE + "/auth/anonymous")
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert client.cookies.get("zg_session") == token


def test_daily_generation_limit_does_not_enqueue_or_consume_another_unit(api_sandbox, monkeypatch):
    verified_config(api_sandbox, monkeypatch)
    client = api_sandbox.anonymous()
    user_id = client.get(BASE + "/auth/session").json()["userId"]
    assert preferences(client).status_code == 200
    now = utcnow()
    day = now.replace(tzinfo=UTC).astimezone(CN).date().isoformat()
    with transaction() as session:
        quota = policy(session)["generationsPerDay"]
        bucket = locked_bucket(session, "generate:" + user_id + ":" + day, next_slot("00:00", now))
        bucket.count = quota
    response = client.post(BASE + "/me/briefs", json={"preferenceVersion": 1}, headers={"Idempotency-Key": api_sandbox.prefix + "-limited"})
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    with transaction() as session:
        assert not list(session.scalars(select(Run).where(Run.user_id == user_id)))
        bucket = locked_bucket(session, "generate:" + user_id + ":" + day, next_slot("00:00", now))
        assert bucket.count == quota


def test_expired_cookie_creates_new_identity_but_never_recovers_another_users_data(api_sandbox):
    client = api_sandbox.anonymous()
    original = client.get(BASE + "/auth/session").json()["userId"]
    assert preferences(client).status_code == 200
    with transaction() as session:
        login = session.get(SessionToken, digest(client.cookies.get("zg_session")))
        login.expires_at = utcnow() - timedelta(seconds=1)
    assert client.get(BASE + "/auth/session").status_code == 401
    replacement = assert_dto(client.post(BASE + "/auth/anonymous"), "Session")
    api_sandbox.users.add(replacement["userId"])
    assert replacement["userId"] != original and replacement["onboardingCompleted"] is False
    assert client.get(BASE + "/me/preferences").json()["version"] == 0


@pytest.mark.parametrize("source_type", ["rss", "newsnow"])
def test_brief_and_delivery_enforce_owner_before_actions(api_sandbox, source_type):
    owner = api_sandbox.anonymous()
    other = api_sandbox.anonymous()
    user_id = owner.get(BASE + "/auth/session").json()["userId"]
    run_id, brief_id, delivery_id = (api_sandbox.prefix + suffix for suffix in ("_run", "_brief", "_delivery"))
    timestamp = iso(utcnow())
    brief_data = dict(id=brief_id, title="Synthetic owner-only brief", date="2026-09-19", version=1, summary="Synthetic fixture", items=[], generationStatus="completed", deliveryStatus="submitted", generatedAt=timestamp, missingSources=[])
    item = dict(
        id="synthetic-news", title="Synthetic news", summary="Synthetic summary", topic="test",
        reason="Internal recommendation reason", source="Synthetic source", sourceType=source_type,
        publishedAt=timestamp, fetchedAt=timestamp, snapshotId="synthetic-snapshot",
        url="https://example.test/news",
        citations=[dict(id="synthetic-news", name="Synthetic source", title="Synthetic news",
                        url="https://example.test/news", publishedAt=timestamp)],
    )
    brief_data["items"] = [item]
    with transaction() as session:
        session.add(Run(id=run_id, user_id=user_id, business_key=api_sandbox.prefix, status="completed", preferences={"version": 1, "role": "", "topics": ["test"], "keywords": []}, config={"version": "synthetic-v1", "modelId": "synthetic-model"}, brief_id=brief_id))
        session.flush()
        session.add(Brief(id=brief_id, user_id=user_id, run_id=run_id, date="2026-09-19", version=1, data=brief_data, published=True))
        session.flush()
        session.add(Delivery(id=delivery_id, user_id=user_id, brief_id=brief_id, status="submitted", attempts=1))
    detail = assert_dto(owner.get(BASE + f"/me/briefs/{brief_id}"), "Brief")
    listing = assert_dto(owner.get(BASE + "/me/briefs"), "BriefPage")
    listed = next(brief for brief in listing["items"] if brief["id"] == brief_id)
    expected_item = {key: value for key, value in item.items() if key not in {"reason", "citations"}}
    assert detail["items"] == listed["items"] == [expected_item]
    with transaction() as session:
        assert session.get(Brief, brief_id).data["items"] == [item]
    assert other.get(BASE + f"/me/briefs/{brief_id}").status_code == 404
    assert other.post(BASE + f"/me/deliveries/{delivery_id}/retry", headers={"Idempotency-Key": api_sandbox.prefix + "-retry"}).status_code == 404
    with transaction() as session:
        assert session.get(Delivery, delivery_id).attempts == 1


def test_blocked_cookie_does_not_create_replacement_account(api_sandbox):
    admin = api_sandbox.admin()
    client = api_sandbox.anonymous()
    identity = client.get(BASE + "/auth/session").json()["userId"]
    token = client.cookies.get("zg_session")
    response = admin.put(BASE + f"/admin/anonymous-accounts/{identity}/status", json={"status": "blocked", "reason": "Synthetic acceptance block"})
    assert_dto(response, "AnonymousAccount")
    blocked = client.post(BASE + "/auth/anonymous")
    assert blocked.status_code == 403 and blocked.json()["code"] == "ACCOUNT_BLOCKED"
    assert client.cookies.get("zg_session") == token
    assert client.get(BASE + "/me/preferences").status_code == 403
    assert_dto(admin.put(BASE + f"/admin/anonymous-accounts/{identity}/status", json={"status": "active", "reason": "Synthetic acceptance restore"}), "AnonymousAccount")
    assert client.get(BASE + "/auth/session").json()["userId"] == identity


def test_every_management_read_requires_independent_admin_authentication(api_sandbox):
    client = api_sandbox.anonymous()
    for path, methods in CONTRACT["paths"].items():
        if path.startswith("/admin/") and "get" in methods and "{" not in path:
            response = client.get(BASE + path)
            assert response.status_code == 403, (path, response.text)
    for removed in ("/me/runs", "/me/runs/not-a-run", "/me/runs/not-a-run/events"):
        assert client.get(BASE + removed).status_code == 404


def test_read_endpoints_return_contract_pagination_and_no_private_keys(api_sandbox):
    client = api_sandbox.anonymous()
    admin = api_sandbox.admin()
    for path, schema_name in [
        ("/me/briefs", "BriefPage"), ("/me/deliveries", "DeliveryPage"),
    ]:
        payload = assert_dto(client.get(BASE + path), schema_name)
        assert payload["items"] == []
    for path, schema_name in [
        ("/admin/sources", "SourcePage"), ("/admin/runs", "AgentRunPage"),
        ("/admin/anonymous-accounts", "AnonymousAccountPage"),
        ("/admin/abuse-events", "AbuseEventPage"), ("/admin/deliveries", "DeliveryPage"),
    ]:
        payload = assert_dto(admin.get(BASE + path, params={"limit": 1}), schema_name)
        assert len(payload["items"]) <= (10 if schema_name == "SourcePage" else 1)
        assert "apiKey" not in str(payload) and "token_hash" not in str(payload)
    assert_dto(admin.get(BASE + "/admin/overview"), "HealthSummary")
    assert_dto(admin.get(BASE + "/admin/anonymous-policy"), "AnonymousPolicy")
