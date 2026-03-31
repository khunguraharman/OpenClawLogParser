create schema if not exists openclaw_logs;

create table if not exists openclaw_logs.log_metadata (
    log_metadata_id bigint generated always as identity primary key,
    logger_name text not null,
    parent_names text[],
    runtime text,
    runtime_version text,
    hostname text,
    source_method text,
    source_full_file_path text,
    source_file_path text,
    source_file_name text,
    source_file_line integer,
    source_file_column integer,
    created_at timestamptz not null default now(),
    check (source_file_line is null or source_file_line >= 0),
    check (source_file_column is null or source_file_column >= 0)
);

comment on table openclaw_logs.log_metadata is
    'Normalized metadata from each row''s _meta object so queries can group and filter by logger, runtime, host, and source callsite.';

comment on column openclaw_logs.log_metadata.logger_name is
    'Usually mirrors the logger or JSON-encoded subsystem/module string from _meta.name.';

create unique index if not exists log_metadata_natural_key_idx
    on openclaw_logs.log_metadata (
        coalesce(logger_name, ''),
        coalesce(parent_names, '{}'::text[]),
        coalesce(runtime, ''),
        coalesce(runtime_version, ''),
        coalesce(hostname, ''),
        coalesce(source_method, ''),
        coalesce(source_full_file_path, ''),
        coalesce(source_file_path, ''),
        coalesce(source_file_name, ''),
        coalesce(source_file_line, -1),
        coalesce(source_file_column, -1)
    );

create index if not exists log_metadata_logger_idx
    on openclaw_logs.log_metadata (logger_name);

create index if not exists log_metadata_source_path_idx
    on openclaw_logs.log_metadata (source_file_path);

create index if not exists log_metadata_parent_names_gin_idx
    on openclaw_logs.log_metadata using gin (parent_names);

create table if not exists openclaw_logs.log_entries (
    log_entry_id bigint generated always as identity primary key,
    log_metadata_id bigint not null references openclaw_logs.log_metadata(log_metadata_id),
    line_number integer,
    logged_at timestamptz not null,
    meta_date timestamptz,
    log_level_id integer,
    log_level_name text,
    context_raw text not null,
    context_json jsonb,
    field1_text text,
    field1_json jsonb,
    field2_text text,
    field2_json jsonb,
    raw_record jsonb not null,
    inserted_at timestamptz not null default now(),
    check (line_number is null or line_number > 0)
);

comment on table openclaw_logs.log_entries is
    'One row per JSON log line. Stores per-event timestamps, level, payload fragments, and the full raw record.';

comment on column openclaw_logs.log_entries.logged_at is
    'Top-level time field from the log line.';

comment on column openclaw_logs.log_entries.meta_date is
    'Timestamp from _meta.date. This is usually close to, but distinct from, logged_at.';

comment on column openclaw_logs.log_entries.context_raw is
    'Original value from JSON key "0". In these logs it is often a JSON-encoded subsystem/module object, but it can also be plain text.';

comment on column openclaw_logs.log_entries.context_json is
    'Parsed JSON form of key "0" when context_raw contains JSON.';

comment on column openclaw_logs.log_entries.field1_text is
    'Text form of key "1" when the source value is plain text.';

comment on column openclaw_logs.log_entries.field1_json is
    'JSONB form of key "1" when the source value is structured JSON.';

comment on column openclaw_logs.log_entries.field2_text is
    'Text form of key "2" when the source value is plain text.';

comment on column openclaw_logs.log_entries.field2_json is
    'JSONB form of key "2" when the source value is structured JSON.';

create index if not exists log_entries_logged_at_idx
    on openclaw_logs.log_entries (logged_at);

create index if not exists log_entries_level_time_idx
    on openclaw_logs.log_entries (log_level_name, logged_at);

create index if not exists log_entries_metadata_time_idx
    on openclaw_logs.log_entries (log_metadata_id, logged_at);

create index if not exists log_entries_context_json_gin_idx
    on openclaw_logs.log_entries using gin (context_json);

create index if not exists log_entries_raw_record_gin_idx
    on openclaw_logs.log_entries using gin (raw_record);
