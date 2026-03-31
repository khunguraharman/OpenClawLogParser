from __future__ import annotations

from collections.abc import Sequence
import json
import os
from pathlib import Path
from typing import Any

from .config import DEFAULT_POSTGRES_HOST, DEFAULT_POSTGRES_PORT
from .parser import LogMetadataPayload, ParsedLogRecord
from .tailer import Checkpoint


class PostgresSink:
    def __init__(
        self,
        database: str,
        state_file: Path,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        try:
            import psycopg  # type: ignore[import-not-found]
            from psycopg.types.json import Jsonb  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on local environment
            raise RuntimeError(
                "psycopg is required for Postgres ingestion. Install dependencies with 'pip install -r requirements.txt'."
            ) from exc

        self._psycopg = psycopg
        self._Jsonb = Jsonb
        self._database = database
        self._user = user
        self._password = password
        self._state_file = state_file
        self._connection = None
        self._metadata_cache: dict[tuple[Any, ...], int] = {}
        self._checkpoints: dict[tuple[str, str], Checkpoint] = {}
        self._state_loaded = False

    def ensure_ready(self) -> None:
        state_parent = self._state_file.resolve().parent
        state_parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def load_checkpoint(self, consumer_name: str, log_path: str) -> Checkpoint | None:
        self._load_state()
        return self._checkpoints.get((consumer_name, log_path))

    def persist_batch(self, checkpoint: Checkpoint, events: Sequence[ParsedLogRecord]) -> int:
        connection = self._ensure_connection()
        inserted_count = 0
        with connection.transaction():
            with connection.cursor() as cursor:
                for event in events:
                    metadata_id = self._resolve_metadata_id(cursor, event.metadata)
                    context_json = self._jsonb_or_none(event.context_json)
                    field1_json = self._jsonb_or_none(event.field1_json)
                    field2_json = self._jsonb_or_none(event.field2_json)
                    raw_record = self._Jsonb(event.raw_record)

                    cursor.execute(
                        """
                        insert into openclaw_logs.log_entries (
                            log_metadata_id,
                            line_number,
                            logged_at,
                            meta_date,
                            log_level_id,
                            log_level_name,
                            context_raw,
                            context_json,
                            field1_text,
                            field1_json,
                            field2_text,
                            field2_json,
                            raw_record
                        )
                        select %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        where not exists (
                            select 1
                            from openclaw_logs.log_entries
                            where log_metadata_id = %s
                              and line_number is not distinct from %s
                              and logged_at = %s
                              and meta_date is not distinct from %s
                              and log_level_id is not distinct from %s
                              and log_level_name is not distinct from %s
                              and context_raw = %s
                              and context_json is not distinct from %s
                              and field1_text is not distinct from %s
                              and field1_json is not distinct from %s
                              and field2_text is not distinct from %s
                              and field2_json is not distinct from %s
                              and raw_record = %s
                        )
                        """,
                        (
                            metadata_id,
                            event.line_number,
                            event.logged_at,
                            event.meta_date,
                            event.log_level_id,
                            event.log_level_name,
                            event.context_raw,
                            context_json,
                            event.field1_text,
                            field1_json,
                            event.field2_text,
                            field2_json,
                            raw_record,
                            metadata_id,
                            event.line_number,
                            event.logged_at,
                            event.meta_date,
                            event.log_level_id,
                            event.log_level_name,
                            event.context_raw,
                            context_json,
                            event.field1_text,
                            field1_json,
                            event.field2_text,
                            field2_json,
                            raw_record,
                        ),
                    )
                    inserted_count += cursor.rowcount

        self._checkpoints[(checkpoint.consumer_name, checkpoint.log_path)] = checkpoint
        self._save_state()
        return inserted_count

    def close(self) -> None:
        if self._connection is not None and not self._connection.closed:
            self._connection.close()

    def _resolve_metadata_id(self, cursor, metadata: LogMetadataPayload) -> int:
        natural_key = metadata.natural_key()
        cached = self._metadata_cache.get(natural_key)
        if cached is not None:
            return cached

        parent_names = list(metadata.parent_names) if metadata.parent_names is not None else None
        cursor.execute(
            """
            insert into openclaw_logs.log_metadata (
                logger_name,
                parent_names,
                runtime,
                runtime_version,
                hostname,
                source_method,
                source_full_file_path,
                source_file_path,
                source_file_name,
                source_file_line,
                source_file_column
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict do nothing
            returning log_metadata_id
            """,
            (
                metadata.logger_name,
                parent_names,
                metadata.runtime,
                metadata.runtime_version,
                metadata.hostname,
                metadata.source_method,
                metadata.source_full_file_path,
                metadata.source_file_path,
                metadata.source_file_name,
                metadata.source_file_line,
                metadata.source_file_column,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                """
                select log_metadata_id
                from openclaw_logs.log_metadata
                where coalesce(logger_name, '') = coalesce(%s, '')
                  and coalesce(parent_names, '{}'::text[]) = coalesce(%s, '{}'::text[])
                  and coalesce(runtime, '') = coalesce(%s, '')
                  and coalesce(runtime_version, '') = coalesce(%s, '')
                  and coalesce(hostname, '') = coalesce(%s, '')
                  and coalesce(source_method, '') = coalesce(%s, '')
                  and coalesce(source_full_file_path, '') = coalesce(%s, '')
                  and coalesce(source_file_path, '') = coalesce(%s, '')
                  and coalesce(source_file_name, '') = coalesce(%s, '')
                  and coalesce(source_file_line, -1) = coalesce(%s, -1)
                  and coalesce(source_file_column, -1) = coalesce(%s, -1)
                """,
                (
                    metadata.logger_name,
                    parent_names,
                    metadata.runtime,
                    metadata.runtime_version,
                    metadata.hostname,
                    metadata.source_method,
                    metadata.source_full_file_path,
                    metadata.source_file_path,
                    metadata.source_file_name,
                    metadata.source_file_line,
                    metadata.source_file_column,
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to resolve log_metadata_id for parsed log metadata.")

        metadata_id = int(row[0])
        self._metadata_cache[natural_key] = metadata_id
        return metadata_id

    def _jsonb_or_none(self, value):
        if value is None:
            return None
        return self._Jsonb(value)

    def _ensure_connection(self):
        if self._connection is None or self._connection.closed:
            connect_kwargs: dict[str, object] = {
                "host": DEFAULT_POSTGRES_HOST,
                "port": DEFAULT_POSTGRES_PORT,
                "dbname": self._database,
            }
            if self._user:
                connect_kwargs["user"] = self._user
            if self._password:
                connect_kwargs["password"] = self._password
            self._connection = self._psycopg.connect(**connect_kwargs)
        return self._connection

    def _load_state(self) -> None:
        if self._state_loaded:
            return

        self._state_loaded = True
        if not self._state_file.exists():
            self._checkpoints = {}
            return

        payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        checkpoints = payload.get("checkpoints", {})
        loaded: dict[tuple[str, str], Checkpoint] = {}
        for key, value in checkpoints.items():
            consumer_name, log_path = key.split("||", 1)
            loaded[(consumer_name, log_path)] = Checkpoint(
                consumer_name=consumer_name,
                log_path=log_path,
                file_device=value.get("file_device"),
                file_inode=value.get("file_inode"),
                byte_offset=int(value["byte_offset"]),
                line_number=int(value["line_number"]),
            )
        self._checkpoints = loaded

    def _save_state(self) -> None:
        payload = {
            "version": 1,
            "checkpoints": {
                f"{consumer_name}||{log_path}": {
                    "file_device": checkpoint.file_device,
                    "file_inode": checkpoint.file_inode,
                    "byte_offset": checkpoint.byte_offset,
                    "line_number": checkpoint.line_number,
                }
                for (consumer_name, log_path), checkpoint in sorted(self._checkpoints.items())
            },
        }

        target_path = self._state_file.resolve()
        temp_path = target_path.with_name(f"{target_path.name}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp_path, target_path)
