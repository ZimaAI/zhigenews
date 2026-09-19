import hashlib
import hmac
import ipaddress
import json
import re
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert

from .db import Bucket, Resource, SessionToken, User, iso, uid, utcnow
from .errors import AppError
from .settings import get_settings

DEFAULT_POLICY = dict(
    requestsPerMinute=60, generationsPerDay=20, maxConcurrentGenerations=1, accountsPerIpHour=10
)
USER_COOKIE = "zg_session"
ADMIN_COOKIE = "zg_admin_session"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def password_hash(password):
    salt = secrets.token_bytes(16)
    return salt.hex() + ":" + hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()


def check_password(password, stored):
    try:
        salt, expected = stored.split(":")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(expected, actual)
    except (ValueError, AttributeError):
        return False


def encrypt(value):
    key = get_settings().secret_encryption_key
    if not key:
        raise AppError("CONFIGURATION_REQUIRED", "服务器尚未配置凭据加密密钥", 503)
    return Fernet(key.encode()).encrypt(value.encode()).decode()


def decrypt(value):
    return (
        Fernet(get_settings().secret_encryption_key.encode()).decrypt(value.encode()).decode()
        if value
        else ""
    )


def redact(value):
    """Events contain summaries only, never provider request dumps or credentials."""
    text = str(value)
    text = re.sub(r"(?i)(bearer\s+|api[_-]?key[\"'\s:=]+)[\w\-\.]+", r"\1[redacted]", text)
    text = re.sub(r"\bsk-[\w-]+", "[redacted]", text)
    return text[:4000]


def client_ip(request):
    peer = request.client.host if request.client else "127.0.0.1"
    try:
        address = ipaddress.ip_address(peer)
        trusted = [ipaddress.ip_network(c) for c in get_settings().trusted_proxy_cidrs]
        if any(address in c for c in trusted):
            chain = request.headers.get("x-forwarded-for", "").split(",")
            for entry in reversed(chain):
                candidate = ipaddress.ip_address(entry.strip())
                if not any(candidate in c for c in trusted):
                    return str(candidate)
        return str(address)
    except ValueError:
        return peer


def ip_hash(request):
    key = get_settings().ip_hash_key
    if not key:
        raise AppError("CONFIGURATION_REQUIRED", "服务器尚未初始化安全配置", 503)
    return hmac.new(key.encode(), client_ip(request).encode(), hashlib.sha256).hexdigest()


def policy(session):
    record = session.get(Resource, "anonymous-policy")
    return dict(record.data) if record else dict(DEFAULT_POLICY)


def locked_bucket(session, key, expires_at):
    statement = insert(Bucket).values(key=key, count=0, expires_at=expires_at)
    session.execute(statement.on_duplicate_key_update(key=statement.inserted.key))
    return session.scalar(select(Bucket).where(Bucket.key == key).with_for_update())


def audit(session, account_id, kind, detail, actor=None):
    ident = uid("ev_")
    session.add(
        Resource(
            id=ident,
            kind="abuse",
            data=dict(id=ident, accountId=account_id, time=iso(utcnow()), kind=kind, detail=redact(detail)),
            private={"actor": actor},
        )
    )


def issue_session(session, user, response):
    token = secrets.token_urlsafe(32)
    settings = get_settings()
    age = (
        settings.admin_session_hours * 3600
        if user.role == "admin"
        else settings.anonymous_session_days * 86400
    )
    session.add(
        SessionToken(
            token_hash=digest(token),
            user_id=user.id,
            kind=user.role,
            expires_at=utcnow() + timedelta(seconds=age),
        )
    )
    response.set_cookie(
        ADMIN_COOKIE if user.role == "admin" else USER_COOKIE,
        token,
        max_age=age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def authenticated(session, request, admin=False, *, optional=False, lock=False):
    token = request.cookies.get(ADMIN_COOKIE if admin else USER_COOKIE)
    login = session.get(SessionToken, digest(token)) if token else None
    expected = "admin" if admin else "anonymous"
    if not login or login.revoked or login.expires_at <= utcnow() or login.kind != expected:
        if optional:
            return None
        raise AppError(
            "FORBIDDEN" if admin and request.cookies.get(USER_COOKIE) else "UNAUTHENTICATED",
            "需要管理员登录" if admin else "会话已失效",
            403 if admin and request.cookies.get(USER_COOKIE) else 401,
        )
    query = select(User).where(User.id == login.user_id)
    user = session.scalar(query.with_for_update() if lock else query)
    if user.status == "blocked":
        raise AppError("ACCOUNT_BLOCKED", "此匿名账号已被停用", 403)
    return user


def public_session(user):
    result = dict(kind=user.role, userId=user.id, name=user.name)
    if user.role == "anonymous":
        result["onboardingCompleted"] = user.onboarding
    return result
