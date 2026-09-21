from copy import deepcopy

from zhigenews.application import public_brief
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
