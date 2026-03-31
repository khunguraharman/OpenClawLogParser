from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any


JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


@dataclass(frozen=True)
class LogMetadataPayload:
    logger_name: str
    parent_names: tuple[str, ...] | None
    runtime: str | None
    runtime_version: str | None
    hostname: str | None
    source_method: str | None
    source_full_file_path: str | None
    source_file_path: str | None
    source_file_name: str | None
    source_file_line: int | None
    source_file_column: int | None

    def natural_key(self) -> tuple[Any, ...]:
        return (
            self.logger_name,
            self.parent_names,
            self.runtime,
            self.runtime_version,
            self.hostname,
            self.source_method,
            self.source_full_file_path,
            self.source_file_path,
            self.source_file_name,
            self.source_file_line,
            self.source_file_column,
        )


@dataclass(frozen=True)
class ParsedLogRecord:
    line_number: int
    logged_at: datetime
    meta_date: datetime | None
    log_level_id: int | None
    log_level_name: str | None
    context_raw: str
    context_json: JsonValue
    field1_text: str | None
    field1_json: JsonValue
    field2_text: str | None
    field2_json: JsonValue
    raw_record: dict[str, Any]
    metadata: LogMetadataPayload


def parse_log_line(raw_line: str, line_number: int) -> ParsedLogRecord | None:
    text = raw_line.strip()
    if not text:
        return None

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Log line must decode to a JSON object.")

    meta = payload.get("_meta")
    if not isinstance(meta, dict):
        meta = {}

    path_meta = meta.get("path")
    if not isinstance(path_meta, dict):
        path_meta = {}

    meta_date = _parse_timestamp(meta.get("date"))
    logged_at = _parse_timestamp(payload.get("time")) or meta_date
    if logged_at is None:
        raise ValueError("Log line is missing both 'time' and '_meta.date'.")

    context_value = payload.get("0", "")
    context_raw = _stringify(context_value)

    return ParsedLogRecord(
        line_number=line_number,
        logged_at=logged_at,
        meta_date=meta_date,
        log_level_id=_parse_int(meta.get("logLevelId")),
        log_level_name=_as_optional_text(meta.get("logLevelName")),
        context_raw=context_raw,
        context_json=_parse_embedded_json(context_raw),
        field1_text=_field_text(payload.get("1")),
        field1_json=_field_json(payload.get("1")),
        field2_text=_field_text(payload.get("2")),
        field2_json=_field_json(payload.get("2")),
        raw_record=payload,
        metadata=LogMetadataPayload(
            logger_name=_as_optional_text(meta.get("name")) or "",
            parent_names=_parent_names(meta.get("parentNames")),
            runtime=_as_optional_text(meta.get("runtime")),
            runtime_version=_as_optional_text(meta.get("runtimeVersion")),
            hostname=_as_optional_text(meta.get("hostname")),
            source_method=_as_optional_text(path_meta.get("method")),
            source_full_file_path=_as_optional_text(path_meta.get("fullFilePath")),
            source_file_path=_as_optional_text(path_meta.get("filePath")),
            source_file_name=_as_optional_text(path_meta.get("fileName")),
            source_file_line=_parse_int(path_meta.get("fileLine")),
            source_file_column=_parse_int(path_meta.get("fileColumn")),
        ),
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"Cannot parse integer from {value!r}")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _parse_embedded_json(value: str) -> JsonValue:
    stripped = value.strip()
    if not stripped or stripped[0] not in "{[":
        return None

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _field_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return None


def _field_json(value: Any) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, str):
        return None
    return value


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _parent_names(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("Expected _meta.parentNames to be a JSON array.")
    return tuple(str(item) for item in value)
