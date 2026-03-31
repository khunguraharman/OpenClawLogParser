from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
import time
from typing import Protocol, Sequence

from .config import IngestorConfig
from .health import HealthServer, HealthSnapshot
from .parser import ParsedLogRecord, parse_log_line
from .tailer import Checkpoint, FileTailer, LogFileLocator


LOGGER = logging.getLogger(__name__)


class EventSink(Protocol):
    def ensure_ready(self) -> None: ...

    def load_checkpoint(self, consumer_name: str, log_path: str) -> Checkpoint | None: ...

    def persist_batch(self, checkpoint: Checkpoint, events: Sequence[ParsedLogRecord]) -> int: ...

    def close(self) -> None: ...


class DryRunSink:
    def __init__(self) -> None:
        self._checkpoints: dict[tuple[str, str], Checkpoint] = {}
        self.inserted_event_count = 0

    def ensure_ready(self) -> None:
        return

    def load_checkpoint(self, consumer_name: str, log_path: str) -> Checkpoint | None:
        return self._checkpoints.get((consumer_name, log_path))

    def persist_batch(self, checkpoint: Checkpoint, events: Sequence[ParsedLogRecord]) -> int:
        self._checkpoints[(checkpoint.consumer_name, checkpoint.log_path)] = checkpoint
        self.inserted_event_count += len(events)
        return len(events)

    def close(self) -> None:
        return


class IngestorService:
    def __init__(self, config: IngestorConfig, sink: EventSink, dry_run: bool = False) -> None:
        self._config = config
        self._sink = sink
        self._dry_run = dry_run
        self._locator = LogFileLocator(
            directory=config.log_directory,
            exact_file=config.log_file,
            glob_pattern=config.log_glob,
        )
        self._tailer = FileTailer(config.consumer_name, config.start_position)
        self._health_lock = threading.Lock()
        self._health_snapshot = HealthSnapshot(consumer_name=config.consumer_name, dry_run=dry_run)
        self._health_server: HealthServer | None = None
        self._active_checkpoint: Checkpoint | None = None
        self._active_log_path: str | None = None

    def run_forever(self) -> None:
        self._start()
        try:
            while True:
                try:
                    processed_lines = self.poll_once()
                except Exception as exc:
                    LOGGER.exception("Polling failed: %s", exc)
                    self._set_health(last_error=str(exc))
                    time.sleep(self._config.poll_interval_seconds)
                    continue

                if processed_lines == 0:
                    time.sleep(self._config.poll_interval_seconds)
        finally:
            self._stop()

    def run_once(self) -> int:
        self._start()
        try:
            total_processed = 0
            while True:
                processed_lines = self.poll_once()
                total_processed += processed_lines
                if processed_lines == 0:
                    return total_processed
        finally:
            self._stop()

    def poll_once(self) -> int:
        self._set_health(last_poll_at=datetime.now(timezone.utc), last_error=None)

        active_file = self._locator.find_active_file()
        if active_file is None:
            LOGGER.info("No matching log file found yet.")
            self._set_health(active_log_path=None)
            return 0

        resolved_log_path = str(active_file.resolve())
        checkpoint = self._load_checkpoint_for_path(resolved_log_path, active_file)

        batch = self._tailer.read_batch(active_file, checkpoint, self._config.batch_size)
        if not batch.lines:
            self._active_checkpoint = batch.checkpoint
            self._set_health(active_log_path=resolved_log_path, byte_offset=batch.checkpoint.byte_offset)
            return 0

        parsed_events: list[ParsedLogRecord] = []
        for raw_line in batch.lines:
            try:
                parsed = parse_log_line(raw_line.text, raw_line.line_number)
            except Exception as exc:
                LOGGER.warning(
                    "Skipping malformed log line %s in %s: %s",
                    raw_line.line_number,
                    resolved_log_path,
                    exc,
                )
                continue

            if parsed is not None:
                parsed_events.append(parsed)

        inserted_count = self._sink.persist_batch(batch.checkpoint, parsed_events)
        self._active_checkpoint = batch.checkpoint

        LOGGER.info(
            "Processed %s lines from %s (%s inserted).",
            len(batch.lines),
            resolved_log_path,
            inserted_count,
        )
        current_snapshot = self._snapshot()
        self._set_health(
            active_log_path=resolved_log_path,
            byte_offset=batch.checkpoint.byte_offset,
            processed_lines=current_snapshot.processed_lines + inserted_count,
            last_ingested_at=datetime.now(timezone.utc),
            last_error=None,
        )
        return len(batch.lines)

    def snapshot(self) -> HealthSnapshot:
        return self._snapshot()

    def _start(self) -> None:
        self._sink.ensure_ready()
        if self._config.health_port is not None and self._config.health_host is not None and self._health_server is None:
            self._health_server = HealthServer(self._config.health_host, self._config.health_port, self._snapshot)
            self._health_server.start()

    def _stop(self) -> None:
        if self._health_server is not None:
            self._health_server.stop()
            self._health_server = None
        self._sink.close()

    def _load_checkpoint_for_path(self, resolved_log_path: str, active_file_path: Path) -> Checkpoint:
        if self._active_checkpoint is not None and self._active_log_path == resolved_log_path:
            return self._active_checkpoint

        checkpoint = self._sink.load_checkpoint(self._config.consumer_name, resolved_log_path)
        if checkpoint is None:
            checkpoint = self._tailer.initial_checkpoint(active_file_path)

        self._active_checkpoint = checkpoint
        self._active_log_path = resolved_log_path
        return checkpoint

    def _snapshot(self) -> HealthSnapshot:
        with self._health_lock:
            return replace(self._health_snapshot)

    def _set_health(self, **updates) -> None:
        with self._health_lock:
            self._health_snapshot = replace(self._health_snapshot, **updates)
