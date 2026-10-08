import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

TRUE_VALUES = {"true", "on", "yes", "1"}
FALSE_VALUES = {"false", "off", "no", "0"}

@dataclass
class ParsedValue:
    path: str
    name: str
    value_type: str
    value: Any

def classify_payload(payload: bytes) -> tuple[str, Any, str | None]:
    text = payload.decode("utf-8", errors="replace")
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered in TRUE_VALUES:
        return "boolean", True, text
    if lowered in FALSE_VALUES:
        return "boolean", False, text
    try:
        number = float(stripped)
        return "number", number, text
    except ValueError:
        pass
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            return "json", parsed, text
        if isinstance(parsed, bool):
            return "boolean", parsed, text
        if isinstance(parsed, (int, float)):
            return "number", float(parsed), text
        if parsed is None:
            return "empty", None, text
        return "text", str(parsed), text
    except (json.JSONDecodeError, TypeError):
        pass
    if not text:
        return "empty", None, text
    return "text", text, text

def _type_for(value: Any) -> str:
    if isinstance(value, bool): return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool): return "number"
    if isinstance(value, str): return "text"
    if value is None: return "null"
    return "json"

def flatten_scalars(value: Any, prefix: str = "") -> list[ParsedValue]:
    if isinstance(value, dict):
        result = []
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.extend(flatten_scalars(child, path))
        return result
    if isinstance(value, list):
        result = []
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            result.extend(flatten_scalars(child, path))
        return result
    return [ParsedValue(prefix or "value", prefix.rsplit(".", 1)[-1] or "value", _type_for(value), value)]

def parse_payload(payload: bytes) -> tuple[str, Any, list[ParsedValue], str | None]:
    payload_type, value, text = classify_payload(payload)
    if payload_type == "json":
        fields = flatten_scalars(value)
    elif payload_type in {"boolean", "number", "text", "empty"}:
        fields = [ParsedValue("value", "value", payload_type, value)]
    else:
        fields = []
    return payload_type, value, fields, text

def payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

def as_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
