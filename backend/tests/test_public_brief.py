from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from zhigenews.application import progress, public_brief
from zhigenews.contract import schema, validate
from zhigenews.db import Brief


def test_public_brief_omits_missing_sources_without_changing_stored_data():
    stored = dict(
        id="synthetic-brief",
        title="Synthetic partial brief",
        date="2026-09-21",
        version=1,
        summary="Synthetic fixture",
        items=[],
        generationStatus="partial",
        deliveryStatus="submitted",
        generatedAt="2026-09-21T00:00:00Z",
        missingSources=["Synthetic source limitation"],
    )
    original = deepcopy(stored)
    brief = Brief(data=stored)

    payload = public_brief(brief)

    validate(schema("Brief"), payload, output=True)
    assert "missingSources" not in payload
    assert payload == {key: value for key, value in original.items() if key != "missingSources"}
    assert brief.data == original


@pytest.mark.parametrize(("status", "private", "expected"), [
    ("queued", {}, "preparing"),
    ("running", {}, "preparing"),
    ("running", {"harnessStarted": True}, "researching"),
    ("running", {"harnessStarted": True, "outputBriefId": "brief"}, "publishing"),
    ("partial", {"outputBriefId": "brief"}, None),
    ("failed", {"harnessStarted": True}, None),
])
def test_reader_progress_uses_business_phase_and_hides_internal_errors(status, private, expected):
    private = {**private, "phaseStartedAt": "2026-09-21T00:00:00Z"}
    run = SimpleNamespace(id="run", status=status, private=private, percent=95, remaining_seconds=None,
                          updated_at=datetime(2026, 9, 21, 0, 5), brief_id=None,
                          error="Internal model budget and missing-source details")
    payload = progress(run)
    validate(schema("GenerationProgress"), payload, output=True)
    assert payload["phase"] == expected
    assert payload["phaseStartedAt"] == (private["phaseStartedAt"] if expected else None)
    assert payload["error"] == ("生成失败，请重试" if status == "failed" else "")
