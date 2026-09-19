"""The three remaining production cookie/IP acceptance boundaries, on real MySQL."""

import hashlib
import hmac
import ipaddress
from datetime import timedelta
from http.cookies import SimpleCookie

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from zhigenews.db import Bucket, User, transaction, utcnow
from zhigenews.security import locked_bucket, policy
from zhigenews.settings import get_settings

pytestmark = pytest.mark.mysql
BASE = "/api/v1"


def _address(sandbox, suffix=1):
    unique = sandbox.prefix[-12:]
    return str(ipaddress.ip_address(f"2001:db8:{unique[:4]}:{unique[4:8]}:{unique[8:]}::{suffix}"))


def _hash_ip(address):
    return hmac.new(get_settings().ip_hash_key.encode(), address.encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def account_ip_buckets():
    """Remove only these tests' unique IP quota rows, including boundary-hour fixtures."""
    hashes = set()
    yield hashes
    with transaction() as session:
        for address_hash in hashes:
            session.execute(delete(Bucket).where(Bucket.key.like("account:" + address_hash + ":%")))


def _client(sandbox, buckets, peer, *, expected_ip=None, forwarded=None, https=False):
    headers = {"X-Zhige-Request": "1", "Origin": "http://127.0.0.1:5173"}
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    client = TestClient(
        sandbox.app,
        base_url="https://testserver" if https else "http://testserver",
        client=(peer, 41999),
        headers=headers,
    )
    sandbox.clients.append(client)
    buckets.add(_hash_ip(expected_ip or peer))
    return client


def _create(sandbox, client):
    response = client.post(BASE + "/auth/anonymous")
    assert response.status_code == 200, response.text
    identity = response.json()["userId"]
    sandbox.users.add(identity)
    return response, identity


def test_production_secure_cookie_is_issued_and_restores_over_https(
    api_sandbox, account_ip_buckets, monkeypatch
):
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    client = _client(api_sandbox, account_ip_buckets, _address(api_sandbox), https=True)
    response, identity = _create(api_sandbox, client)
    cookies = SimpleCookie()
    cookies.load(response.headers["set-cookie"])
    cookie = cookies["zg_session"]
    assert cookie["secure"] and cookie["httponly"]
    assert cookie["samesite"].lower() == "lax" and cookie["path"] == "/"
    assert not cookie["domain"]
    restored = client.get(BASE + "/auth/session")
    assert restored.status_code == 200 and restored.json()["userId"] == identity


def test_clearing_cookie_does_not_reset_same_ip_creation_quota(api_sandbox, account_ip_buckets, monkeypatch):
    monkeypatch.setattr(get_settings(), "cookie_secure", False)
    address = _address(api_sandbox)
    client = _client(api_sandbox, account_ip_buckets, address)
    _, identity = _create(api_sandbox, client)
    address_hash = _hash_ip(address)
    hour = utcnow().replace(minute=0, second=0, microsecond=0)
    with transaction() as session:
        assert session.scalar(select(func.count(User.id)).where(User.ip_hash == address_hash)) == 1
        quota = policy(session)["accountsPerIpHour"]
        # Start immediately at the real configured boundary without creating quota-many accounts.
        for start in (hour, hour + timedelta(hours=1)):
            bucket = locked_bucket(
                session, "account:" + address_hash + ":" + start.isoformat(), start + timedelta(hours=1)
            )
            bucket.count = quota
    # An existing valid identity still restores: only creation consumes this IP quota.
    restored = client.post(BASE + "/auth/anonymous")
    assert restored.status_code == 200 and restored.json()["userId"] == identity
    client.cookies.clear()
    rejected = client.post(BASE + "/auth/anonymous")
    assert rejected.status_code == 429 and rejected.json()["code"] == "RATE_LIMITED"
    assert int(rejected.headers["Retry-After"]) > 0
    assert "set-cookie" not in rejected.headers
    with transaction() as session:
        assert session.scalar(select(func.count(User.id)).where(User.ip_hash == address_hash)) == 1
    different_ip = _client(api_sandbox, account_ip_buckets, _address(api_sandbox, suffix=2))
    _, different_identity = _create(api_sandbox, different_ip)
    assert different_identity != identity


@pytest.mark.parametrize("path", ["untrusted_peer", "trusted_peer", "trusted_chain"])
def test_forwarded_ip_affects_account_identity_only_at_trusted_proxy_boundary(
    api_sandbox, account_ip_buckets, monkeypatch, path
):
    monkeypatch.setattr(get_settings(), "cookie_secure", False)
    monkeypatch.setattr(get_settings(), "trusted_proxy_cidrs", ["10.9.0.0/24"])
    external = _address(api_sandbox)
    if path == "untrusted_peer":
        peer, forwarded, expected = external, "203.0.113.123", external
    elif path == "trusted_peer":
        peer, forwarded, expected = "10.9.0.2", external, external
    else:
        # A client-supplied leftmost entry cannot cross the rightmost untrusted hop.
        peer, forwarded, expected = "10.9.0.2", f"203.0.113.123, {external}, 10.9.0.1", external
    client = _client(api_sandbox, account_ip_buckets, peer, expected_ip=expected, forwarded=forwarded)
    _, identity = _create(api_sandbox, client)
    with transaction() as session:
        assert session.get(User, identity).ip_hash == _hash_ip(expected)
        keys = list(
            session.scalars(select(Bucket.key).where(Bucket.key.like("account:" + _hash_ip(expected) + ":%")))
        )
        assert len(keys) == 1
