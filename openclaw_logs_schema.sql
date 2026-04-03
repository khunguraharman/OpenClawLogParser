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
    run_id uuid,
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

comment on column openclaw_logs.log_entries.run_id is
    'Run identifier extracted from key "1".runId when present. Null for log lines that are not associated with a run.';

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

create index if not exists log_entries_run_id_idx
    on openclaw_logs.log_entries (run_id);

create index if not exists log_entries_level_time_idx
    on openclaw_logs.log_entries (log_level_name, logged_at);

create index if not exists log_entries_metadata_time_idx
    on openclaw_logs.log_entries (log_metadata_id, logged_at);

create index if not exists log_entries_run_time_idx
    on openclaw_logs.log_entries (run_id, logged_at);

create index if not exists log_entries_context_json_gin_idx
    on openclaw_logs.log_entries using gin (context_json);

create index if not exists log_entries_raw_record_gin_idx
    on openclaw_logs.log_entries using gin (raw_record);

create table if not exists openclaw_logs.agent_operation_observability (
    run_id uuid primary key,
    trace_started_at timestamptz,
    trace_finished_at timestamptz,
    end_to_end_trace_ms numeric(18,3),
    agent_to_agent_handoff_latency_ms numeric(18,3),
    cost_per_request_usd numeric(12,6),
    notes text,
    measured_at timestamptz not null default now(),
    check (trace_started_at is null or trace_finished_at is null or trace_finished_at >= trace_started_at),
    check (end_to_end_trace_ms is null or end_to_end_trace_ms >= 0),
    check (agent_to_agent_handoff_latency_ms is null or agent_to_agent_handoff_latency_ms >= 0),
    check (cost_per_request_usd is null or cost_per_request_usd >= 0)
);

comment on table openclaw_logs.agent_operation_observability is
    'Run-level observability metrics. For the current single-agent sample logs, agent_to_agent_handoff_latency_ms will typically remain null.';

comment on column openclaw_logs.agent_operation_observability.end_to_end_trace_ms is
    'Elapsed time in milliseconds across the full run trace, usually from the earliest run log to the latest run log.';

comment on column openclaw_logs.agent_operation_observability.agent_to_agent_handoff_latency_ms is
    'Latency between one agent handing work to another. Expected to be null for single-agent runs.';

comment on column openclaw_logs.agent_operation_observability.cost_per_request_usd is
    'Estimated request cost in USD. Leave null when the logs do not expose enough billing or token detail to calculate it.';

create table if not exists openclaw_logs.agent_operation_evaluation (
    run_id uuid primary key,
    task_completion_percentage numeric(5,2),
    guardrail_violation_rate numeric(5,2) not null default 0,
    factual_accuracy_rate numeric(5,2) not null default 0,
    notes text,
    measured_at timestamptz not null default now(),
    check (task_completion_percentage is null or task_completion_percentage between 0 and 100),
    check (guardrail_violation_rate between 0 and 100),
    check (factual_accuracy_rate between 0 and 100)
);

comment on table openclaw_logs.agent_operation_evaluation is
    'Run-level evaluation metrics. Guardrail and factual accuracy rates currently default to 0 because those systems are not yet configured.';

comment on column openclaw_logs.agent_operation_evaluation.task_completion_percentage is
    'Percent of the intended task completed for the run. Leave null when completion cannot yet be scored automatically.';

create table if not exists openclaw_logs.agent_operation_optimization (
    run_id uuid primary key,
    prompt_token_efficiency numeric(12,4),
    retrieval_precision_at_k numeric(5,2),
    retrieval_k integer,
    handoff_success_rate numeric(5,2) not null default 100,
    notes text,
    measured_at timestamptz not null default now(),
    check (prompt_token_efficiency is null or prompt_token_efficiency >= 0),
    check (retrieval_precision_at_k is null or retrieval_precision_at_k between 0 and 100),
    check (retrieval_k is null or retrieval_k > 0),
    check (handoff_success_rate between 0 and 100)
);

comment on table openclaw_logs.agent_operation_optimization is
    'Run-level optimization metrics. Handoff success defaults to 100 for the current single-agent setup.';

comment on column openclaw_logs.agent_operation_optimization.prompt_token_efficiency is
    'Implementation-defined efficiency score for prompt token usage. Leave null until a scoring formula is chosen.';

comment on column openclaw_logs.agent_operation_optimization.retrieval_precision_at_k is
    'Percentage of top-K retrieved items that were relevant. Leave null for runs with no retrieval activity.';
