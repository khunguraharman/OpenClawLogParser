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
        from .postgres import PostgresSink

        sink = PostgresSink(
            database=config.postgres_database,
            state_file=config.state_file,
            user=config.postgres_user,
            password=config.postgres_password,
        )

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
    parser.add_argument("--database", help="Postgres database name on localhost:5432. Default: postgres")
    parser.add_argument("--user", help="Optional Postgres username for localhost auth.")
    parser.add_argument("--password", help="Optional Postgres password for localhost auth.")
    parser.add_argument("--state-file", type=Path, help="Local JSON checkpoint file used to resume after restarts.")
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
        postgres_database=args.database or config.postgres_database,
        postgres_user=args.user if args.user is not None else config.postgres_user,
        postgres_password=args.password if args.password is not None else config.postgres_password,
        log_directory=config.log_directory,
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
