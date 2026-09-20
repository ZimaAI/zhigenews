"""Exercise every approved operation against MySQL, with explicit synthetic records."""

import json

import pytest
from test_api import verified_config

from zhigenews.contract import CONTRACT, schema, validate
from zhigenews.db import Brief, Delivery, Resource, Run, RunEvent, iso, transaction, utcnow
from zhigenews.security import decrypt

pytestmark = pytest.mark.mysql


class ContractProbe:
    def __init__(self, sandbox):
        self.sandbox, self.seen = sandbox, set()
        self.operations = {
            operation["operationId"]: (method, path, operation)
            for path, methods in CONTRACT["paths"].items()
            for method, operation in methods.items()
        }

    def call(self, operation_id, client, *, ident=None, body=None, params=None, headers=None, status=None):
        method, path, operation = self.operations[operation_id]
        if ident:
            path = path.replace("{id}", ident)
        supplied_headers = dict(headers or {})
        if any(parameter["name"] == "Idempotency-Key" for parameter in operation.get("parameters", [])):
            supplied_headers.setdefault("Idempotency-Key", self.sandbox.prefix + "-" + operation_id)
        response = client.request(method, "/api/v1" + path, json=body, params=params, headers=supplied_headers)
        expected = status if status is not None else next(int(code) for code in operation["responses"] if code.isdigit() and int(code) < 300)
        assert response.status_code == expected, (operation_id, response.text)
        definition = operation["responses"][str(response.status_code)]
        if "$ref" in definition:
            definition = CONTRACT["components"]["responses"][definition["$ref"].rsplit("/", 1)[-1]]
        content = definition.get("content", {})
        if "application/json" in content:
            validate(content["application/json"]["schema"], response.json(), output=True)
        elif "text/event-stream" in content:
            assert response.headers["content-type"].startswith("text/event-stream")
            for line in response.text.splitlines():
                if line.startswith("data: "):
                    validate(schema("RunEvent"), json.loads(line[6:]), output=True)
        else:
            assert response.content == b""
        self.seen.add(operation_id)
        return response


def test_all_active_operations_return_their_real_http_contract(api_sandbox, monkeypatch):
    probe = ContractProbe(api_sandbox)
    config = verified_config(api_sandbox, monkeypatch)
    user, admin = api_sandbox.anonymous(), api_sandbox.admin()
    probe.call("ensureAnonymousSession", user)
    identity = probe.call("getSession", user).json()["userId"]
    probe.call("adminLogin", admin, body=api_sandbox.admin_credentials)
    probe.call("getAdminSession", admin)
    probe.call("getPreferences", user)
    probe.call("savePreferences", user, body={"version": 0, "role": "Synthetic reader", "topics": ["Agent"], "keywords": []})
    probe.call("getDeliverySettings", user)
    probe.call("saveDeliverySettings", user, body={"time": "09:35"})

    source_write = {"name": api_sandbox.prefix + " RSS", "kind": "rss", "sourceId": "", "url": "https://fixture.invalid/feed.xml", "interval": 900}
    source = probe.call("createSource", admin, body=source_write).json()
    api_sandbox.resource(source["id"])
    probe.call("getSource", admin, ident=source["id"])
    probe.call("saveSource", admin, ident=source["id"], body={**source_write, "interval": 1200, "version": source["version"]})
    probe.call("setSourceEnabled", admin, ident=source["id"], body={"enabled": False})
    probe.call("setSourceEnabled", admin, ident=source["id"], body={"enabled": True})
    probe.call("fetchSource", admin, ident=source["id"])
    probe.call("listSources", admin)
    probe.call("stopSource", admin, ident=source["id"])
    probe.call("batchSources", admin, body={"action": "disable", "ids": [source["id"]]})
    probe.call("deleteInvalidSources", user, status=403)
    probe.call("currentSourceDeletion", admin)

    generation = probe.call("generateBrief", user, body={"preferenceVersion": 1}).json()
    probe.call("getCurrentGeneration", user)
    probe.call("getGenerationProgress", user, ident=generation["id"])
    probe.call("cancelGeneration", user, ident=generation["id"])
    probe.call("cancelAdminRun", admin, ident=generation["id"])
    probe.call("listAdminRuns", admin)
    probe.call("getAdminRun", admin, ident=generation["id"])

    brief_id, delivery_id = api_sandbox.prefix + "_brief", api_sandbox.prefix + "_delivery"
    now = utcnow()
    timestamp = iso(now)
    brief = dict(id=brief_id, title="Synthetic contract brief", date=timestamp[:10], version=1, summary="Synthetic evidence", items=[], generationStatus="completed", deliveryStatus="failed", generatedAt=timestamp, missingSources=[])
    with transaction() as session:
        run = session.get(Run, generation["id"])
        run.status, run.percent, run.brief_id = "completed", 100, brief_id
        session.add(Brief(id=brief_id, user_id=identity, run_id=run.id, date=timestamp[:10], version=1, data=brief, published=True))
        session.flush()
        session.add(Delivery(id=delivery_id, user_id=identity, brief_id=brief_id, status="failed", attempts=1))
        for seq in (1, 2):
            event = dict(id=seq, time=timestamp, title="Synthetic persistent event", detail="Synthetic contract-only fixture", status="completed", duration="1ms")
            session.add(RunEvent(run_id=run.id, seq=seq, data=event))
    probe.call("listBriefs", user, params={"q": "Synthetic contract", "limit": 1})
    probe.call("getBrief", user, ident=brief_id)
    probe.call("listOwnDeliveries", user)
    probe.call("retryOwnDelivery", user, ident=delivery_id)
    probe.call("listAdminDeliveries", admin)
    probe.call("retryAdminDelivery", admin, ident=delivery_id)
    events = probe.call("adminRunEvents", admin, ident=generation["id"], headers={"Last-Event-ID": "1"})
    assert "id: 1\n" not in events.text and "id: 2\n" in events.text
    assert "event: run.event\n" in events.text

    case_write = {"name": api_sandbox.prefix + " fixed case", "preference": "Agent", "expected": "Evidence remains fixed", "sourceSnapshotIds": [], "fixedAt": timestamp}
    case = probe.call("createEvalCase", admin, body=case_write).json()
    api_sandbox.resource(case["id"])
    updated = probe.call("saveEvalCase", admin, ident=case["id"], body={"name": case["name"], "preference": "Agent", "expected": "Updated synthetic expectation"}).json()
    assert updated["fixedAt"] == case["fixedAt"] and updated["revision"] == 2
    probe.call("listEvalCases", admin)
    probe.call("runEvaluation", admin, body={"configVersion": config["version"]}, status=400)
    accepted = probe.call("runEvaluation", admin, body={}).json()
    evaluation_id = api_sandbox.resource(accepted["evaluationId"])
    evaluation = probe.call("getEvaluation", admin, ident=evaluation_id).json()
    assert evaluation["relevance"] is None and evaluation["citations"] is None
    assert evaluation["configVersion"] == config["version"]
    assert evaluation["modelId"] == "synthetic-test-model"
    probe.call("listEvaluations", admin)
    with transaction() as session:
        private = session.get(Resource, evaluation_id).private
        frozen = private["snapshot"]
        own = next(row for row in frozen["cases"] if row["id"] == case["id"])
        assert own["revision"] == 2 and own["sourceSnapshotIds"] == []
        assert private["config"] == config and private["judge"] is None
        for model in private["models"].values():
            assert model["data"]["modelId"] == "synthetic-test-model"
            assert decrypt(model["encryptedSecret"]) == "synthetic-model-secret-" + api_sandbox.prefix
            assert model["encryptedSecret"] not in str(evaluation)
        assert "synthetic-model-secret-" not in str(evaluation)
        assert config["systemPrompt"] not in str(evaluation)
    probe.call("saveEvalCase", admin, ident=case["id"], body={"name": case["name"], "preference": "Different", "expected": "Later edit"})
    with transaction() as session:
        frozen = session.get(Resource, evaluation_id).private["snapshot"]
        assert next(row for row in frozen["cases"] if row["id"] == case["id"])["revision"] == 2

    probe.call("getOverview", admin)
    probe.call("listAnonymousAccounts", admin)
    probe.call("setAnonymousAccountStatus", admin, ident=identity, body={"status": "blocked", "reason": "Synthetic contract block"})
    probe.call("setAnonymousAccountStatus", admin, ident=identity, body={"status": "active", "reason": "Synthetic contract restore"})
    probe.call("listAbuseEvents", admin)
    current_policy = probe.call("getAnonymousPolicy", admin).json()
    probe.call("saveAnonymousPolicy", admin, body=current_policy)
    probe.call("adminLogout", admin)
    assert probe.seen == set(probe.operations), sorted(set(probe.operations) - probe.seen)
