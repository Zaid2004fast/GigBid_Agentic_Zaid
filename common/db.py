"""Application database (SQLAlchemy Core). Postgres in docker/prod, SQLite locally.

Every table that holds user data has a `user_id` column and every query in the API is
scoped by it (tenant isolation, E4).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import (JSON, Boolean, Column, Float, Index, Integer, MetaData, String, Table, Text, UniqueConstraint,
                        create_engine)
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
md = MetaData()

users = Table("users", md,
              Column("id", String, primary_key=True), Column("email", String, unique=True, nullable=False),
              Column("password_hash", String, nullable=False), Column("name", String), Column("persona", String),
              Column("created_at", Float), Column("is_reviewer", Boolean, default=False))

settings = Table("user_settings", md,
                 Column("user_id", String, primary_key=True), Column("data", JSON, nullable=False))

oauth_tokens = Table("oauth_tokens", md,
                     Column("user_id", String, primary_key=True), Column("provider", String, primary_key=True),
                     Column("ciphertext", Text, nullable=False), Column("expires_at", Float), Column("updated_at", Float))

saved_searches = Table("saved_searches", md,
                       Column("id", String, primary_key=True), Column("user_id", String, index=True),
                       Column("query", String), Column("category", String), Column("skills", String),
                       Column("interval_minutes", Integer), Column("next_run_at", Float), Column("last_seen_posted_at", Float),
                       Column("enabled", Boolean, default=True))

jobs = Table("jobs", md,
             Column("user_id", String, primary_key=True), Column("job_id", String, primary_key=True),
             Column("fingerprint", String, index=True), Column("data", JSON), Column("status", String),
             Column("fit", Float), Column("risk", Float), Column("action", String), Column("price", Float),
             Column("connects", Integer), Column("thread_id", String), Column("duplicate_of", String),
             Column("created_at", Float), Column("updated_at", Float))

runs = Table("runs", md,
             Column("thread_id", String, primary_key=True), Column("user_id", String, index=True),
             Column("graph", String), Column("job_id", String), Column("status", String), Column("trace_id", String),
             Column("started_at", Float), Column("ended_at", Float), Column("latency_s", Float),
             Column("tokens", Integer, default=0), Column("cost_usd", Float, default=0.0), Column("summary", JSON),
             Column("attention_reason", String))

run_events = Table("run_events", md,
                   Column("id", Integer, primary_key=True, autoincrement=True), Column("thread_id", String, index=True),
                   Column("user_id", String), Column("ts", Float), Column("event", JSON))

spans = Table("spans", md,
              Column("span_id", String, primary_key=True), Column("trace_id", String, index=True),
              Column("parent_id", String), Column("user_id", String), Column("thread_id", String, index=True),
              Column("name", String), Column("kind", String), Column("start", Float), Column("end", Float),
              Column("status", String), Column("attrs", JSON), Column("tokens_in", Integer, default=0),
              Column("tokens_out", Integer, default=0), Column("cost_usd", Float, default=0.0), Column("model", String))

pipeline = Table("pipeline", md,
                 Column("user_id", String, primary_key=True), Column("job_id", String, primary_key=True),
                 Column("stage", String), Column("proposal_id", String), Column("title", String),
                 Column("category", String), Column("connects", Integer), Column("price", Float),
                 Column("updated_at", Float), Column("history", JSON))

edits = Table("edits", md,
              Column("id", String, primary_key=True), Column("user_id", String, index=True), Column("job_id", String),
              Column("kind", String), Column("before", Text), Column("after", Text), Column("diff", JSON), Column("ts", Float))

rejections = Table("rejections", md,
                   Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, index=True),
                   Column("job_id", String), Column("reason", String), Column("ts", Float))

submissions = Table("submissions", md,
                    Column("idempotency_key", String, primary_key=True), Column("user_id", String),
                    Column("job_id", String), Column("kind", String), Column("result", JSON), Column("ts", Float),
                    UniqueConstraint("idempotency_key", name="uq_submission_key"))

queue = Table("work_queue", md,
              Column("key", String, primary_key=True), Column("user_id", String), Column("kind", String),
              Column("payload", JSON), Column("status", String), Column("attempts", Integer, default=0),
              Column("last_error", String), Column("created_at", Float), Column("updated_at", Float))

Index("ix_jobs_user_status", jobs.c.user_id, jobs.c.status)


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url.replace("postgresql://", "postgresql+psycopg://") if url.startswith("postgresql://") else url
    p = ROOT / "data" / "processed" / "gigbid.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{p.as_posix()}"


@lru_cache(maxsize=1)
def engine() -> Engine:
    url = database_url()
    kw = {"connect_args": {"check_same_thread": False, "timeout": 30}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    e = create_engine(url, future=True, **kw)
    if url.startswith("sqlite"):
        with e.begin() as c:
            c.exec_driver_sql("PRAGMA journal_mode=WAL")
    md.create_all(e)
    return e
