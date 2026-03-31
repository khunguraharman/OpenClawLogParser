from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

DEFAULT_LOG_DIRECTORY = Path("/tmp/openclaw")
DEFAULT_STATE_FILE = Path("/tmp/openclaw/openclaw_log_parser_state.json")
DEFAULT_POSTGRES_HOST = "127.0.0.1"
DEFAULT_POSTGRES_PORT = 5432


@dataclass(frozen=True)
class IngestorConfig:
    postgres_database: str
    postgres_user: str | None
    postgres_password: str | None
    log_directory: Path
    state_file: Path
    poll_interval_seconds: float
    batch_size: int
    start_position: str
    consumer_name: str
    health_host: str | None
    health_port: int | None
    log_level: str

    @classmethod
    def from_env(cls) -> "IngestorConfig":
        health_port_raw = os.getenv("OPENCLAW_HEALTH_PORT")
        health_port = int(health_port_raw) if health_port_raw else None
        health_host = os.getenv("OPENCLAW_HEALTH_HOST", "127.0.0.1") if health_port else None

        state_file_raw = os.getenv("OPENCLAW_STATE_FILE")
        state_file = Path(state_file_raw).expanduser() if state_file_raw else DEFAULT_STATE_FILE

        log_directory_raw = os.getenv("OPENCLAW_LOG_DIRECTORY")
        if log_directory_raw:
            log_directory = Path(log_directory_raw).expanduser()
        else:
            log_directory = DEFAULT_LOG_DIRECTORY

        start_position = os.getenv("OPENCLAW_START_POSITION", "end").lower()
        if start_position not in {"beginning", "end"}:
            raise ValueError("OPENCLAW_START_POSITION must be either 'beginning' or 'end'.")

        batch_size = int(os.getenv("OPENCLAW_BATCH_SIZE", "250"))
        if batch_size <= 0:
            raise ValueError("OPENCLAW_BATCH_SIZE must be greater than zero.")

        poll_interval_seconds = float(os.getenv("OPENCLAW_POLL_INTERVAL_SECONDS", "5"))
        if poll_interval_seconds <= 0:
            raise ValueError("OPENCLAW_POLL_INTERVAL_SECONDS must be greater than zero.")

        return cls(
            postgres_database=os.getenv("OPENCLAW_POSTGRES_DATABASE", "postgres"),
            postgres_user=os.getenv("OPENCLAW_POSTGRES_USER"),
            postgres_password=os.getenv("OPENCLAW_POSTGRES_PASSWORD"),
            log_directory=log_directory,
            state_file=state_file,
            poll_interval_seconds=poll_interval_seconds,
            batch_size=batch_size,
            start_position=start_position,
            consumer_name=os.getenv("OPENCLAW_CONSUMER_NAME", "openclaw-log-parser"),
            health_host=health_host,
            health_port=health_port,
            log_level=os.getenv("OPENCLAW_LOG_LEVEL", "INFO").upper(),
        )
