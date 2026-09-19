"""Development/operations CLI. Initialization is additive and never resets data."""

import argparse
import json

from sqlalchemy import select

from .db import Resource, User, iso, transaction, uid, utcnow
from .harness import mysql_persistence
from .ingestion.catalog import default_sources
from .security import encrypt, password_hash
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
        if s.openai_api_key and s.openai_model and not session.get(Resource, "initial-model"):
            model = dict(
                id="initial-model",
                name="初始模型",
                provider="OpenAI-compatible",
                modelId=s.openai_model,
                endpoint=s.openai_base_url,
                keyMasked="已设置",
                role="主模型",
                enabled=True,
                verified=False,
                contextWindow=32768,
            )
            session.add(
                Resource(id="initial-model", kind="model", data=model, secret=encrypt(s.openai_api_key))
            )
            config = dict(
                id="initial-config",
                name="每日新闻",
                version="initial-v1",
                status="draft",
                modelId="initial-model",
                summaryModelId="initial-model",
                maxModelCalls=20,
                maxToolCalls=40,
                maxSeconds=180,
                summaryTokens=12000,
                summaryMessages=30,
                summaryRatio=0.7,
                subagentConcurrency=2,
                tools=[
                    "list_dir",
                    "read_file",
                    "search_content",
                    "write_file",
                    "bash",
                    "web_search",
                    "delegate_research",
                ],
                systemPrompt="你是知更新闻编辑。按用户话题、背景与关键词检索可信新闻，核对引用，生成简洁中文摘要和推荐理由。证据不足时明确说明，不编造新闻。",
            )
            session.add(Resource(id="initial-config", kind="config", data=config))
    with mysql_persistence(s.database_url, setup=True):
        pass
    print(
        "Database initialized. Model remains unverified and config remains draft until an actual capability test."
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
