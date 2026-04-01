# OpenClaw Log Parser

This background script watches the active OpenClaw daily log file, reads only completed appended lines, parses each JSON log event, and writes it into the `openclaw_logs` Postgres tables defined by `openclaw_logs_schema.sql`.

It is designed for the MacMini-style deployment you described:

- no GUI
- read-only access to the log files
- no file locking or write blocking
- automatic resume after restart
- optional localhost health endpoint

## How it works

The parser scans `/tmp/openclaw` for files named `openclaw-*.log`, picks the one created most recently, opens it in read-only mode, seeks to its saved byte offset, and only processes lines that end with a newline. If the writer is still appending a partial line, that line is ignored until the next poll, so the logger keeps uninterrupted write access.

Each successful batch is written to Postgres, and the parser stores its read offset in a local JSON state file on the MacMini. That keeps the database schema aligned with `openclaw_logs_schema.sql` while still letting the parser resume after restarts.

## Files

- `openclaw_logs_schema.sql`: the only database schema file the parser relies on
- `openclaw_log_parser.py`: direct script entrypoint
- `openclaw_log_ingestor/`: implementation modules used by the script
- `deploy/com.openclaw.log-parser.plist`: `launchd` template for macOS

## Install

There is no package install step for the parser itself. It runs directly as a script from this folder.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Apply the schema:

```bash
psql -h 127.0.0.1 -p 5432 -U "$OPENCLAW_POSTGRES_USER" -d "$OPENCLAW_POSTGRES_DATABASE" -f openclaw_logs_schema.sql
```

## Configuration

Environment variables:

- `OPENCLAW_POSTGRES_DATABASE`: local database name, default `postgres`
- `OPENCLAW_POSTGRES_USER`: optional local Postgres username
- `OPENCLAW_POSTGRES_PASSWORD`: optional local Postgres password
- `OPENCLAW_STATE_FILE`: local JSON checkpoint file, default `/tmp/openclaw/openclaw_log_parser_state.json`
- `OPENCLAW_START_POSITION`: `end` or `beginning`; default `end`
- `OPENCLAW_POLL_INTERVAL_SECONDS`: default `5`
- `OPENCLAW_BATCH_SIZE`: default `250`
- `OPENCLAW_CONSUMER_NAME`: checkpoint key, default `openclaw-log-parser`
- `OPENCLAW_HEALTH_PORT`: optional health endpoint port
- `OPENCLAW_LOG_LEVEL`: default `INFO`

Fixed assumptions in code:

- Postgres host is always `127.0.0.1`
- Postgres port is always `5432`
- Logs live under `/tmp/openclaw`
- The parser chooses the newest `openclaw-*.log` file in that folder

Optional local override:

- `OPENCLAW_LOG_DIRECTORY` can still be set for testing, but the intended server location is `/tmp/openclaw`

## Run

Long-running service:

```bash
python3 openclaw_log_parser.py
```

One pass over all currently complete lines:

```bash
python3 openclaw_log_parser.py --once
```

Parser validation without touching Postgres:

```bash
OPENCLAW_LOG_DIRECTORY=/path/to/test/logs python3 openclaw_log_parser.py --dry-run --once --start-position beginning
```

Basic background run without `launchd`:

```bash
nohup python3 /opt/openclaw-log-parser/openclaw_log_parser.py >/tmp/openclaw-log-parser.out 2>&1 &
```

## MacMini deployment with launchd

1. Copy this project to the MacMini, for example `/opt/openclaw-log-parser`.
2. Create a virtual environment there and install the requirements.
3. Edit `deploy/com.openclaw.log-parser.plist` so `WorkingDirectory`, database credentials, and optional health port match the server.
4. Copy the plist to either:
   - `~/Library/LaunchAgents/` for a user-scoped service
   - `/Library/LaunchDaemons/` for a system service
5. Load it:

```bash
launchctl load -w ~/Library/LaunchAgents/com.openclaw.log-parser.plist
```

If you enabled `OPENCLAW_HEALTH_PORT`, the process will expose a simple JSON status endpoint on `http://127.0.0.1:<port>/healthz`.

## Notes

- The ingestor skips malformed JSON lines and keeps advancing so one bad line does not stall the whole file.
- `line_number` is tracked per source file from the newline count.
- The parser keeps restart state in a local JSON file instead of creating extra Postgres tables.
- The parser ignores the date embedded in the filename and instead follows the newest log file in `/tmp/openclaw`.
- On a brand-new file with no checkpoint, `OPENCLAW_START_POSITION=end` means the service starts from the current tail and only captures new appends. Use `beginning` if you want backfill behavior instead.
