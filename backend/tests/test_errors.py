"""All error paths use the approved public categories, retaining internal diagnoses."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from zhigenews.contract import schema, validate
from zhigenews.db import transaction, utcnow
from zhigenews.errors import AppError
from zhigenews.security import locked_bucket, policy

BASE = "/api/v1"


@pytest.mark.parametrize(
    ("internal", "status", "public"),
    [
        ("INVALID_INPUT", 400, "VALIDATION_ERROR"),
        ("INVALID_CREDENTIALS", 401, "UNAUTHENTICATED"),
        ("IMMUTABLE_CONFIG", 409, "INVALID_STATE"),
        ("MODEL_UNVERIFIED", 409, "INVALID_STATE"),
        ("IDEMPOTENCY_CONFLICT", 409, "VERSION_CONFLICT"),
        ("CONCURRENCY_LIMIT", 429, "RATE_LIMITED"),
        ("ACCOUNT_CREATION_LIMIT", 429, "RATE_LIMITED"),
        ("CONFIGURATION_REQUIRED", 409, "INVALID_STATE"),
        ("CONFIGURATION_REQUIRED", 503, "DEPENDENCY_UNAVAILABLE"),
        ("MODEL_UNAVAILABLE", 503, "DEPENDENCY_UNAVAILABLE"),
        ("SERVICE_ERROR", 503, "INTERNAL_ERROR"),
        ("FUTURE_INTERNAL_DETAIL", 400, "VALIDATION_ERROR"),
    ],
)
def test_internal_identity_is_preserved_while_public_code_matches_contract(internal, status, public):
    error = AppError(internal, "具体错误原因保留", status)
    assert error.code == internal and error.status == status and error.message == "具体错误原因保留"
    assert error.public_code == public
    validate(
        schema("Error"),
        {"code": error.public_code, "message": error.message, "requestId": "test"},
        output=True,
    )


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    data = response.json()
    validate(schema("Error"), data, output=True)
    assert data["code"] == code
    assert data["requestId"] and data["message"]
    return data


@pytest.mark.mysql
def test_real_gateway_400_401_403_404_409_429_errors_match_frozen_schema(api_sandbox):
    unauthenticated = api_sandbox.client()
    assert_error(unauthenticated.get(BASE + "/auth/session"), 401, "UNAUTHENTICATED")
    assert_error(unauthenticated.get(BASE + "/does-not-exist"), 404, "NOT_FOUND")
    client = api_sandbox.anonymous()
    invalid = assert_error(client.put(BASE + "/me/preferences", json={}), 400, "VALIDATION_ERROR")
    assert invalid["fields"]
    preference = {"version": 0, "role": "", "topics": ["AI"], "keywords": []}
    assert_error(
        client.put(
            BASE + "/me/preferences", json=preference, headers={"Origin": "https://untrusted.invalid"}
        ),
        403,
        "CSRF_REJECTED",
    )
    assert client.put(BASE + "/me/preferences", json=preference).status_code == 200
    assert_error(client.put(BASE + "/me/preferences", json=preference), 409, "VERSION_CONFLICT")
    user_id = client.get(BASE + "/auth/session").json()["userId"]
    minute = utcnow().replace(second=0, microsecond=0)
    with transaction() as session:
        for start in (minute, minute + timedelta(minutes=1)):
            bucket = locked_bucket(
                session, "request:" + user_id + ":" + start.isoformat(), start + timedelta(minutes=1)
            )
            bucket.count = policy(session)["requestsPerMinute"]
    limited = client.get(BASE + "/me/preferences")
    assert_error(limited, 429, "RATE_LIMITED")
    assert int(limited.headers["Retry-After"]) > 0


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (AppError("CONFIGURATION_REQUIRED", "尚未配置运行依赖", 503), "DEPENDENCY_UNAVAILABLE"),
        (SQLAlchemyError("Synthetic unavailable dependency"), "DEPENDENCY_UNAVAILABLE"),
        (RuntimeError("Synthetic private detail"), "INTERNAL_ERROR"),
    ],
)
def test_gateway_503_domain_database_and_unexpected_paths_match_contract(monkeypatch, exception, expected):
    from zhigenews import gateway

    def unavailable(*args, **kwargs):
        raise exception

    monkeypatch.setattr(gateway, "execute", unavailable)
    with TestClient(gateway.app, raise_server_exceptions=False) as client:
        response = client.get(BASE + "/auth/session")
        data = assert_error(response, 503, expected)
        assert "Synthetic" not in data["message"]
