"""Frozen initial schema and real MySQL installation/persistence checks.

Set MIGRATION_ADMIN_DATABASE_URL to an administrative MySQL 8.4 URL to run the
live test. Each execution creates a random zg_migration_test_* schema and drops
only that exact schema. It never migrates, clears or drops the application DB.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from zhigenews.db import Base

BACKEND = Path(__file__).resolve().parents[1]
INITIAL = BACKEND / "migrations" / "versions" / "0001_initial.py"
TEMP_SCHEMA = re.compile(r"^zg_migration_test_[0-9a-f]{24}$")


def test_initial_revision_contains_explicit_frozen_schema():
    source = INITIAL.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name and name.startswith("zhigenews") for name in imported)
    assert "metadata.create_all" not in source and "metadata.drop_all" not in source
    assert "op.create_table" in source and "op.drop_table" in source


def _run_child(command, env):
    result = subprocess.run(
        command,
        cwd=BACKEND.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    if result.returncode:
        # Do not echo a connection string if a driver includes it in an error.
        detail = result.stderr + result.stdout
        for name in ("DATABASE_URL", "MIGRATION_ADMIN_DATABASE_URL"):
            value = env.get(name)
            if value:
                detail = detail.replace(value, "[database URL redacted]")
                password = make_url(value).password
                if password:
                    detail = detail.replace(password, "[redacted]")
        pytest.fail("Migration subprocess failed:\n" + detail[-5000:])
    return result.stdout


@pytest.mark.mysql
def test_mysql_clean_install_repeated_upgrade_and_new_process_persistence():
    admin_setting = os.environ.get("MIGRATION_ADMIN_DATABASE_URL")
    if not admin_setting:
        pytest.skip("Set MIGRATION_ADMIN_DATABASE_URL for the isolated MySQL migration test")
    admin_url = make_url(admin_setting)
    if admin_url.get_backend_name() != "mysql":
        pytest.fail("The initial migration acceptance target must be MySQL 8.4")
    schema_name = "zg_migration_test_" + uuid4().hex[:24]
    assert TEMP_SCHEMA.fullmatch(schema_name)
    assert schema_name != admin_url.database and schema_name != "zhigenews"
    isolated_url = admin_url.set(database=schema_name)
    admin = create_engine(admin_url, pool_pre_ping=True)
    isolated = None
    created = False
    env = {
        **os.environ,
        "DATABASE_URL": isolated_url.render_as_string(hide_password=False),
        "PYTHONIOENCODING": "utf-8",
    }
    try:
        with admin.begin() as connection:
            server_version = connection.scalar(text("SELECT VERSION()"))
            assert server_version.startswith("8.4."), "Migration target is MySQL 8.4"
            connection.execute(
                text(f"CREATE DATABASE `{schema_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            )
            created = True
        upgrade = [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", "head"]
        _run_child(upgrade, env)
        isolated = create_engine(isolated_url, pool_pre_ping=True)
        with isolated.connect() as connection:
            assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
                "alembic_version"
            }
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
            assert differences == [], differences
            options = connection.execute(
                text(
                    "SELECT ENGINE, TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA=:schema AND TABLE_NAME <> 'alembic_version'"
                ),
                {"schema": schema_name},
            ).all()
            assert all(
                engine == "InnoDB" and collation.startswith("utf8mb4_") for engine, collation in options
            )

        writer = """from zhigenews.db import User, Run, Brief, Delivery, Outbox, transaction
with transaction() as session:
    session.add(User(id="migration-reader", name="迁移持久性样例", onboarding=True,
                     preference={"version":1,"role":"工程师","topics":["AI"],"keywords":[]}))
    session.flush()
    session.add(Run(id="migration-run",user_id="migration-reader",business_key="migration-intent",
                    preferences={"version":1},config={"version":"fixture"},status="running"))
    session.flush()
    session.add(Brief(id="migration-brief",user_id="migration-reader",run_id="migration-run",
                      date="2026-09-19",version=1,data={"marker":"persistent JSON"}))
    session.flush()
    session.add(Delivery(id="migration-delivery",user_id="migration-reader",brief_id="migration-brief"))
    session.add(Outbox(id="migration-outbox",kind="delivery",target_id="migration-delivery"))
"""
        _run_child([sys.executable, "-c", writer], env)
        # Second upgrade runs after real business rows exist and must preserve them.
        _run_child(upgrade, env)
        reader = """import json
from zhigenews.db import User, Run, Brief, Delivery, Outbox, transaction
with transaction() as session:
    user=session.get(User,"migration-reader")
    run=session.get(Run,"migration-run")
    brief=session.get(Brief,"migration-brief")
    delivery=session.get(Delivery,"migration-delivery")
    outbox=session.get(Outbox,"migration-outbox")
    assert user.name == "迁移持久性样例" and user.preference["topics"] == ["AI"]
    assert run.business_key == "migration-intent" and run.user_id == user.id
    assert brief.run_id == run.id and brief.data["marker"] == "persistent JSON"
    assert delivery.brief_id == brief.id and outbox.target_id == delivery.id
    print(json.dumps({"persisted":True,"records":5,"unicode":True}))
"""
        outcome = json.loads(_run_child([sys.executable, "-c", reader], env))
        assert outcome == {"persisted": True, "records": 5, "unicode": True}
    finally:
        if isolated:
            isolated.dispose()
        if created:
            # Revalidate the generated, exact target immediately before destructive cleanup.
            if not TEMP_SCHEMA.fullmatch(schema_name) or schema_name in {"zhigenews", admin_url.database}:
                raise RuntimeError("Refusing cleanup outside the exact generated test schema")
            with admin.begin() as connection:
                connection.execute(text(f"DROP DATABASE `{schema_name}`"))
        admin.dispose()
