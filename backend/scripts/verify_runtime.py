"""Run inside the trusted compose worker; uses real HTTP, broker and Docker.

The temporary reader is explicitly synthetic and is removed afterward. This
does not verify a model provider, Tavily, or a real generated brief.
"""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import delete

from zhigenews.db import PreferenceRevision, Resource, SessionToken, User, transaction
from zhigenews.harness.sandbox import DockerSandbox
from zhigenews.settings import get_settings
from zhigenews.workers import celery_app


def main():
    settings = get_settings()
    report = {
        "at": datetime.now(UTC).isoformat(),
        "environment": "Linux compose API + worker + beat + MySQL + Redis",
        "checks": {},
    }
    headers = {"X-Zhige-Request": "1", "Origin": "http://127.0.0.1:5173"}
    user_id = None
    try:
        with httpx.Client(base_url="http://api:8000/api/v1", headers=headers, timeout=15) as user:
            health = user.get("http://api:8000/healthz")
            assert health.status_code == 200
            report["checks"]["health"] = health.json()
            response = user.post("/auth/anonymous")
            assert response.status_code == 200, response.text
            user_id = response.json()["userId"]
            assert user.get("/auth/session").json()["userId"] == user_id
            prefs = {"version": 0, "role": "Runtime smoke synthetic reader", "topics": ["Agent engineering"], "keywords": ["Agent"]}
            response = user.put("/me/preferences", json=prefs)
            assert response.status_code == 200, response.text
            assert user.get("/me/preferences").json()["version"] == 1
            assert user.post("/auth/anonymous").json()["userId"] == user_id
            assert user.get("/admin/overview").status_code == 403
            report["checks"]["anonymous_preferences_cookie"] = "passed; scoped synthetic reader, real HTTP/MySQL"
        with httpx.Client(base_url="http://api:8000/api/v1", headers=headers, timeout=15) as admin:
            response = admin.post("/admin/auth/login", json={"email": settings.admin_email, "password": settings.admin_password})
            assert response.status_code == 200, response.text
            assert admin.get("/admin/overview").status_code == 200
            assert admin.delete("/admin/auth/session").status_code == 204
            assert admin.get("/admin/auth/session").status_code == 401
            report["checks"]["admin_auth"] = "passed; configured local admin, secret omitted"
        pings = celery_app.control.ping(timeout=5)
        assert pings and all("ok" in list(p.values())[0] for p in pings), pings
        report["checks"]["worker_ping"] = pings
        tick = celery_app.send_task("zhigenews.tick").get(timeout=40)
        report["checks"]["broker_worker_task"] = {"status": "passed", "task": "zhigenews.tick", "result": tick}
        with tempfile.TemporaryDirectory(prefix="runtime-probe-", dir=settings.data_dir) as probe:
            root = Path(probe)
            root.chmod(0o755)
            rss = root / "rss"
            rss.mkdir()
            workspace = root / "workspace"
            workspace.mkdir()
            output = workspace / "output"
            output.mkdir()
            (output / "probe.txt").write_text("runtime-probe", encoding="utf-8")
            (output / "probe.txt").chmod(0o644)
            result = DockerSandbox(rss, workspace).run(
                'test "$(id -u)" = 65534 && test ! -e /var/run/docker.sock '
                '&& test "$(cat /workspace/output/probe.txt)" = runtime-probe '
                '&& ! touch /workspace/output/forbidden 2>/dev/null '
                '&& test -z "${OPENAI_API_KEY:-}" && test -z "${TAVILY_API_KEY:-}" '
                "&& echo isolated-runtime-passed", timeout=20,
            )
            assert result["ok"], result
            report["checks"]["worker_nested_sandbox"] = result
        report["status"] = "passed"
    finally:
        if user_id:
            with transaction() as session:
                session.execute(delete(Resource).where(Resource.owner_id == user_id))
                session.execute(delete(PreferenceRevision).where(PreferenceRevision.user_id == user_id))
                session.execute(delete(SessionToken).where(SessionToken.user_id == user_id))
                session.execute(delete(User).where(User.id == user_id))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
