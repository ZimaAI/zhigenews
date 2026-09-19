"""Load the frozen contract; generated DTOs are never a second source of truth."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .errors import AppError

CONTRACT_PATH = Path(__file__).resolve().parent / "contracts" / "openapi.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def validate(schema, value, *, output=False):
    combined = {**schema, "components": CONTRACT["components"]}
    errors = sorted(
        Draft202012Validator(combined, format_checker=FormatChecker()).iter_errors(value),
        key=lambda e: str(e.path),
    )
    if errors:
        if output:
            raise ValueError("Response violates frozen contract: " + "; ".join(e.message for e in errors[:3]))
        # Do not echo rejected body (which can contain passwords / API keys).
        fields = {".".join(map(str, e.path)) or "body": "格式或取值不符合要求" for e in errors[:8]}
        raise AppError("INVALID_INPUT", "请检查输入内容", fields=fields)


def schema(name):
    return {"$ref": "#/components/schemas/" + name}
