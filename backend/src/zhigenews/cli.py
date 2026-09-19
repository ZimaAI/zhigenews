"""Development/operations CLI. Initialization is additive and never resets data."""

import argparse
import json

from sqlalchemy import select

from .db import Resource, User, iso, transaction, uid, utcnow
from .harness import mysql_persistence
from .ingestion.catalog import default_sources
from .security import password_hash
from .settings import get_settings


def initialize():
    s = get_settings()
    if not s.secret_encryption_key or not s.ip_hash_key or len(s.admin_password) < 12:
        raise SystemExit(
            "Configure SECRET_ENCRYPTION_KEY, IP_HASH_KEY and an ADMIN_PASSWORD of at least 12 characters."
        )
    with transaction() as session:
        admin = session.scalar(select(User).where(User.email == s.admin_email.lower(), User.role == "admin"))
        if not admin:
            session.add(
                User(
                    id=uid("admin_"),
                    name="管理员",
                    email=s.admin_email.lower(),
                    role="admin",
                    password_hash=password_hash(s.admin_password),
                )
            )
        for source in default_sources(s.newsnow_base_url):
            if session.get(Resource, source["id"]):
                continue
            data = dict(
                id=source["id"],
                name=source["name"],
                kind=source["kind"],
                sourceId=source["source_id"],
                url=source["url"],
                interval=source["effective_interval_seconds"],
                upstreamInterval=source["upstream_interval_seconds"],
                status="unverified",
                lastSuccess="",
                nextFetch=iso(utcnow()),
                lastChanged="",
                items=0,
                error="",
                snapshotId=None,
                snapshotFetchedAt=None,
                lastFetchedAt=None,
                cacheAgeSeconds=None,
                stale=True,
                upstreamRevision=source.get("upstream_revision"),
            )
            session.add(Resource(id=source["id"], kind="source", data=data, due_at=utcnow()))
    with mysql_persistence(s.database_url, setup=True):
        pass
    print(
        "Database initialized. Models use the configuration file; Agent settings are code constants. "
        "No administrator verification or configuration publishing is required."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "environment", "collect", "tick"])
    args = parser.parse_args()
    if args.command == "init":
        initialize()
    elif args.command == "environment":
        s = get_settings()
        print(
            json.dumps(
                {
                    "databaseConfigured": bool(s.database_url),
                    "encryptionConfigured": bool(s.secret_encryption_key),
                    "openaiConfigured": bool(s.openai_api_key and s.openai_model),
                    "tavilyConfigured": bool(s.tavily_api_key),
                    "langsmithTracing": s.langsmith_tracing,
                    "langsmithConfigured": bool(s.langsmith_api_key.get_secret_value()),
                    "langsmithProject": s.langsmith_project,
                    "sandboxImage": s.sandbox_image,
                },
                indent=2,
            )
        )
    elif args.command == "collect":
        from .workers import collect_source

        with transaction() as session:
            ids = list(session.scalars(select(Resource.id).where(Resource.kind == "source")))
        for ident in ids:
            print(ident, collect_source(ident))
    elif args.command == "tick":
        from .workers import dispatch_outbox, schedule_due

        print(schedule_due())
        print(dispatch_outbox())


if __name__ == "__main__":
    main()
