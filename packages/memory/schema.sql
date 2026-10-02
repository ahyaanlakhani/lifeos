-- Memory store: pgvector schema for LifeOS.
--
-- Run against the existing Supabase database. This is written to be additive
-- and re-runnable: it adds a column beside whatever embedding column already
-- exists rather than replacing it, because the build plan is right that you
-- keep the old one until the new one is verified. Swapping an embedding model
-- is a re-index, and a re-index that goes wrong with no fallback column means
-- recomputing everything from scratch.
--
--   psql "$SUPABASE_DB_URL" -f packages/memory/schema.sql
--
-- Dimensions: 4096, read from the Token Factory console for
-- Qwen3-Embedding-8B on 2 Oct 2026. If the model changes, the column changes,
-- which is the other reason this is a new column and not an ALTER of the old.

create extension if not exists vector;

-- The rows themselves. Mirrors fixtures/memory.json so demo mode and
-- production describe the same thing.
create table if not exists memory_rows (
    id              text primary key,
    kind            text not null,            -- preference | person | fact | commitment | policy
    text            text not null,
    source          text not null,            -- where this came from, in prose
    confidence      real not null default 0.5,
    external_claim  text,                     -- set when the row asserts something about the outside world
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- Grounding, written by the nightly Serverless Job. Kept in its own table so
-- re-running the pass never rewrites the memory rows themselves — the thing
-- being checked and the result of checking it have different lifetimes.
create table if not exists memory_grounding (
    row_id        text primary key references memory_rows(id) on delete cascade,
    status        text not null default 'unverified'
                  check (status in ('confirmed', 'stale', 'contradicted', 'unverified')),
    last_checked  timestamptz,
    note          text,
    sources       jsonb not null default '[]'::jsonb
);

-- The new embedding column, added beside any existing one.
alter table memory_rows add column if not exists embedding_nv vector(4096);

-- Which model produced embedding_nv, so a half-finished re-index is visible
-- rather than silently mixed. Rows whose model does not match the configured
-- one are stale and must be re-embedded before they are trusted for recall.
alter table memory_rows add column if not exists embedding_model text;

create index if not exists memory_rows_embedding_nv_idx
    on memory_rows using hnsw (embedding_nv vector_cosine_ops);

create index if not exists memory_rows_kind_idx on memory_rows (kind);

-- Rows still needing an embedding under the current model. The re-index
-- script drives off this, so it is resumable: kill it halfway and rerun.
create or replace view memory_rows_needing_embedding as
    select id, text, embedding_model
    from memory_rows
    where embedding_nv is null or embedding_model is distinct from current_setting('lifeos.embedding_model', true);

comment on column memory_rows.embedding_nv is
    'Current embedding. Added beside any previous column so a failed re-index can fall back.';
comment on table memory_grounding is
    'Written by jobs/nightly_synthesis. Separate from memory_rows so re-grounding never rewrites what is being grounded.';
