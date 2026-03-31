from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from .config import IngestorConfig
from .service import DryRunSink, IngestorService


def main(argv: list[str] | None = None) -> int:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    config = IngestorConfig.from_env()
    config = _apply_cli_overrides(config, args)

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.dry_run:
        sink = DryRunSink()
    else:
        if not config.postgres_dsn:
            parser.error("Provide OPENCLAW_POSTGRES_DSN or pass --dsn when not using --dry-run.")
        from .postgres import PostgresSink

        sink = PostgresSink(config.postgres_dsn, config.state_file)

    service = IngestorService(config=config, sink=sink, dry_run=args.dry_run)

    try:
        if args.once:
            processed = service.run_once()
            logging.getLogger(__name__).info("Processed %s complete lines.", processed)
            return 0
        service.run_forever()
        return 0
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Stopped by operator.")
        return 0


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll OpenClaw JSON logs and insert appended records into Postgres.",
    )
    parser.add_argument("--dsn", help="Postgres DSN. Overrides OPENCLAW_POSTGRES_DSN.")
    parser.add_argument("--log-directory", type=Path, help="Directory containing daily OpenClaw log files.")
    parser.add_argument("--log-file", type=Path, help="Exact log file to tail instead of auto-discovering the latest.")
    parser.add_argument("--state-file", type=Path, help="Local JSON checkpoint file used to resume after restarts.")
    parser.add_argument("--log-glob", help="Glob used to locate the active log file. Default: openclaw-*.log")
    parser.add_argument(
        "--start-position",
        choices=("beginning", "end"),
        help="Where to start when a file has no checkpoint yet.",
    )
    parser.add_argument("--poll-interval-seconds", type=float, help="Sleep duration when no new lines are available.")
    parser.add_argument("--batch-size", type=int, help="Maximum complete log lines to read per poll.")
    parser.add_argument("--consumer-name", help="Checkpoint key so multiple ingestors can coexist.")
    parser.add_argument("--health-port", type=int, help="Optional localhost health endpoint port.")
    parser.add_argument("--health-host", help="Optional health endpoint host. Default: 127.0.0.1")
    parser.add_argument("--log-level", help="Python logging level. Default: INFO")
    parser.add_argument("--dry-run", action="store_true", help="Parse logs and advance in-memory checkpoints without Postgres writes.")
    parser.add_argument("--once", action="store_true", help="Process all currently available complete lines and then exit.")
    return parser


def _apply_cli_overrides(config: IngestorConfig, args: argparse.Namespace) -> IngestorConfig:
    return IngestorConfig(
        postgres_dsn=args.dsn or config.postgres_dsn,
        log_directory=(args.log_directory or config.log_directory).expanduser(),
        log_glob=args.log_glob if args.log_glob is not None else config.log_glob,
        log_file=(args.log_file.expanduser() if args.log_file else config.log_file),
        state_file=(args.state_file.expanduser() if args.state_file else config.state_file),
        poll_interval_seconds=args.poll_interval_seconds or config.poll_interval_seconds,
        batch_size=args.batch_size or config.batch_size,
        start_position=args.start_position or config.start_position,
        consumer_name=args.consumer_name or config.consumer_name,
        health_host=args.health_host or config.health_host,
        health_port=args.health_port if args.health_port is not None else config.health_port,
        log_level=(args.log_level or config.log_level).upper(),
    )


if __name__ == "__main__":
    sys.exit(main())
