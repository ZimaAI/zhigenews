"""Backend acceptance against the real MySQL gateway; no mocked persistence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, timedelta

import pytest
from sqlalchemy import select

from zhigenews.application import CN, next_slot
from zhigenews.contract import CONTRACT, schema, validate
from zhigenews.db import Brief, Delivery, Resource, Run, SessionToken, User, iso, transaction, utcnow
from zhigenews.security import decrypt, digest, encrypt, locked_bucket, policy

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


def model_body(sandbox):
    return {"name": sandbox.prefix + " model", "provider": "OpenAI-compatible", "modelId": "synthetic-test-model", "endpoint": "https://fixture.invalid/v1", "role": "主模型", "contextWindow": 32000, "apiKey": "synthetic-model-secret-" + sandbox.prefix}


def verified_config(sandbox):
    """Seed only configuration facts; model execution is outside these API tests."""
    model_id = sandbox.resource(sandbox.prefix + "_model")
    config_id = sandbox.resource(sandbox.prefix + "_config")
    model = {"id": model_id, "name": sandbox.prefix, "provider": "OpenAI-compatible", "modelId": "synthetic-test-model", "endpoint": "https://fixture.invalid/v1", "keyMasked": "••••", "role": "主模型", "enabled": True, "verified": True, "contextWindow": 32000}
    config = {"id": config_id, "name": sandbox.prefix, "version": "v99999", "status": "published", "modelId": model_id, "summaryModelId": model_id, "maxModelCalls": 2, "maxToolCalls": 2, "maxSeconds": 10, "summaryTokens": 1000, "summaryMessages": 4, "summaryRatio": 0.7, "subagentConcurrency": 0, "tools": ["list_dir", "read_file"], "systemPrompt": "Synthetic API acceptance configuration; do not contact a real provider."}
    with transaction() as session:
        session.add(Resource(id=model_id, kind="model", data=model, secret=encrypt("synthetic-test-secret")))
        session.add(Resource(id=config_id, kind="config", data=config))
    return config


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


def test_model_secrets_are_encrypted_replaceable_and_revocable(api_sandbox):
    admin = api_sandbox.admin()
    body = model_body(api_sandbox)
    created = assert_dto(admin.post(BASE + "/admin/models", json=body), "ModelConfig", 201)
    api_sandbox.resource(created["id"])
    assert body["apiKey"] not in str(created)
    with transaction() as session:
        record = session.get(Resource, created["id"])
        assert record.secret != body["apiKey"]
        assert decrypt(record.secret) == body["apiKey"]
    replacement = {**body, "apiKey": "synthetic-replacement-key"}
    result = assert_dto(admin.put(BASE + f"/admin/models/{created['id']}", json=replacement), "ModelConfig")
    assert replacement["apiKey"] not in str(result)
    assert admin.delete(BASE + f"/admin/models/{created['id']}/secret").status_code == 204
    with transaction() as session:
        assert not session.get(Resource, created["id"]).secret


def test_model_thinking_setting_persists_and_requires_revalidation(api_sandbox):
    admin = api_sandbox.admin()
    body = {**model_body(api_sandbox), "thinkingEnabled": True}
    created = assert_dto(admin.post(BASE + "/admin/models", json=body), "ModelConfig", 201)
    api_sandbox.resource(created["id"])
    assert created["thinkingEnabled"] is True
    with transaction() as session:
        record = session.get(Resource, created["id"])
        assert record.data["thinkingEnabled"] is True
        record.data = {**record.data, "verified": True}

    # An older client can edit a name without disabling the saved thinking mode.
    edit = {key: value for key, value in body.items() if key not in {"apiKey", "thinkingEnabled"}}
    edit["name"] += " renamed"
    result = assert_dto(admin.put(BASE + f"/admin/models/{created['id']}", json=edit), "ModelConfig")
    assert result["thinkingEnabled"] is True
    assert result["verified"] is True
    listed = assert_dto(admin.get(BASE + "/admin/models?limit=100"), "ModelConfigPage")
    assert next(item for item in listed["items"] if item["id"] == created["id"])["thinkingEnabled"] is True

    edit["thinkingEnabled"] = False
    result = assert_dto(admin.put(BASE + f"/admin/models/{created['id']}", json=edit), "ModelConfig")
    assert result["thinkingEnabled"] is False
    assert result["verified"] is False
    with transaction() as session:
        assert session.get(Resource, created["id"]).data["thinkingEnabled"] is False
    edit["thinkingEnabled"] = "true"
    assert admin.put(BASE + f"/admin/models/{created['id']}", json=edit).status_code == 400


def test_model_thinking_defaults_false_for_new_and_legacy_records(api_sandbox):
    admin = api_sandbox.admin()
    body = model_body(api_sandbox)
    created = assert_dto(admin.post(BASE + "/admin/models", json=body), "ModelConfig", 201)
    api_sandbox.resource(created["id"])
    assert created["thinkingEnabled"] is False
    with transaction() as session:
        record = session.get(Resource, created["id"])
        record.data = {key: value for key, value in record.data.items() if key != "thinkingEnabled"}

    listed = assert_dto(admin.get(BASE + "/admin/models?limit=100"), "ModelConfigPage")
    assert next(item for item in listed["items"] if item["id"] == created["id"])["thinkingEnabled"] is False
    result = assert_dto(admin.put(BASE + f"/admin/models/{created['id']}/enabled", json={"enabled": False}), "ModelConfig")
    assert result["thinkingEnabled"] is False
    edit = {key: value for key, value in body.items() if key != "apiKey"}
    result = assert_dto(admin.put(BASE + f"/admin/models/{created['id']}", json=edit), "ModelConfig")
    assert result["thinkingEnabled"] is False


def test_published_config_cannot_be_overwritten(api_sandbox):
    admin = api_sandbox.admin()
    config = verified_config(api_sandbox)
    write = {key: value for key, value in config.items() if key not in {"id", "version", "status"}}
    write["systemPrompt"] = "This must not alter a published snapshot."
    failure = assert_dto(admin.put(BASE + f"/admin/agent-configs/{config['id']}", json=write), "Error", 409)
    assert failure["code"] == "INVALID_STATE"
    with transaction() as session:
        assert session.get(Resource, config["id"]).data["systemPrompt"] == config["systemPrompt"]


def test_generation_idempotency_current_recovery_and_cross_user_visibility(api_sandbox):
    verified_config(api_sandbox)
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


def test_simultaneous_generation_replays_enqueue_only_one_run(api_sandbox):
    verified_config(api_sandbox)
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
def test_cancel_generation_without_worker(api_sandbox, admin, status, lease_seconds, expected):
    verified_config(api_sandbox)
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


def test_daily_generation_limit_does_not_enqueue_or_consume_another_unit(api_sandbox):
    verified_config(api_sandbox)
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


def test_brief_memory_and_delivery_enforce_owner_before_actions(api_sandbox):
    owner = api_sandbox.anonymous()
    other = api_sandbox.anonymous()
    user_id = owner.get(BASE + "/auth/session").json()["userId"]
    run_id, brief_id, delivery_id = (api_sandbox.prefix + suffix for suffix in ("_run", "_brief", "_delivery"))
    memory_id = api_sandbox.resource(api_sandbox.prefix + "_memory")
    timestamp = iso(utcnow())
    brief_data = dict(id=brief_id, title="Synthetic owner-only brief", date="2026-09-19", version=1, summary="Synthetic fixture", items=[], generationStatus="completed", deliveryStatus="submitted", generatedAt=timestamp, missingSources=[])
    with transaction() as session:
        session.add(Run(id=run_id, user_id=user_id, business_key=api_sandbox.prefix, status="completed", preferences={"version": 1, "role": "", "topics": ["test"], "keywords": []}, config={"version": "synthetic-v1", "modelId": "synthetic-model"}, brief_id=brief_id))
        session.flush()
        session.add(Brief(id=brief_id, user_id=user_id, run_id=run_id, date="2026-09-19", version=1, data=brief_data, published=True))
        session.flush()
        session.add(Delivery(id=delivery_id, user_id=user_id, brief_id=brief_id, status="submitted", attempts=1))
        session.add(Resource(id=memory_id, kind="memory", owner_id=user_id, data=dict(id=memory_id, text="Synthetic user fact", source="explicit-user", updatedAt=timestamp)))
    assert_dto(owner.get(BASE + f"/me/briefs/{brief_id}"), "Brief")
    assert other.get(BASE + f"/me/briefs/{brief_id}").status_code == 404
    assert other.delete(BASE + f"/me/memories/{memory_id}").status_code == 404
    assert other.post(BASE + f"/me/deliveries/{delivery_id}/retry", headers={"Idempotency-Key": api_sandbox.prefix + "-retry"}).status_code == 404
    with transaction() as session:
        assert session.get(Resource, memory_id) is not None
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
        ("/me/briefs", "BriefPage"), ("/me/memories", "MemoryPage"), ("/me/deliveries", "DeliveryPage"),
    ]:
        payload = assert_dto(client.get(BASE + path), schema_name)
        assert payload["items"] == []
    for path, schema_name in [
        ("/admin/sources", "SourcePage"), ("/admin/models", "ModelConfigPage"),
        ("/admin/agent-configs", "AgentConfigPage"), ("/admin/runs", "AgentRunPage"),
        ("/admin/evaluations", "EvaluationPage"), ("/admin/anonymous-accounts", "AnonymousAccountPage"),
        ("/admin/abuse-events", "AbuseEventPage"), ("/admin/deliveries", "DeliveryPage"),
    ]:
        payload = assert_dto(admin.get(BASE + path, params={"limit": 1}), schema_name)
        assert len(payload["items"]) <= 1
        assert "apiKey" not in str(payload) and "token_hash" not in str(payload)
    assert_dto(admin.get(BASE + "/admin/overview"), "HealthSummary")
    assert_dto(admin.get(BASE + "/admin/anonymous-policy"), "AnonymousPolicy")
