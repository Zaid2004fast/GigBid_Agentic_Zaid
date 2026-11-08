"""GigBid Workspace MCP server: calendar slots, tentative interview holds, email drafts.

Backed by a local mock (sqlite) by default - the brief allows this - with the same tool
surface a Google Calendar / Gmail backend would expose (WORKSPACE_BACKEND=google is the
extension point).  The agent only ever sees these MCP tools.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_servers.common import ROOT, AuditLog, call_context

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

DB = Path(os.getenv("WORKSPACE_STATE", ROOT / "data" / "processed" / "workspace.sqlite"))
DB.parent.mkdir(parents=True, exist_ok=True)
_db = sqlite3.connect(DB, check_same_thread=False)
_db.executescript("""
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, user TEXT, start TEXT, end TEXT, title TEXT, status TEXT, idem TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, user TEXT, to_name TEXT, subject TEXT, body TEXT, created TEXT, idem TEXT UNIQUE);
""")
_lock = threading.Lock()
AUDIT = AuditLog(Path(os.getenv("WORKSPACE_AUDIT", ROOT / "data" / "processed" / "audit" / "workspace_audit.jsonl")))

mcp = FastMCP("gigbid-workspace", instructions="Calendar availability, tentative interview holds and email drafts for the freelancer.",
              stateless_http=True, json_response=True)


class Slot(BaseModel):
    start: str = Field(description="ISO-8601 with timezone")
    end: str
    label: str


class Slots(BaseModel):
    timezone: str
    slots: list[Slot]


class HoldIn(BaseModel):
    start: str = Field(description="ISO-8601 start, must be one of the offered free slots")
    duration_minutes: int = Field(30, ge=15, le=120)
    title: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=8, max_length=128)


class Hold(BaseModel):
    event_id: str
    start: str
    end: str
    status: str


class EmailDraftIn(BaseModel):
    to_name: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=3, max_length=150)
    body: str = Field(min_length=10, max_length=5000)
    idempotency_key: str = Field(min_length=8, max_length=128)


class EmailDraft(BaseModel):
    draft_id: str
    subject: str
    status: str


def _busy(user: str) -> list[tuple[dt.datetime, dt.datetime]]:
    with _lock:
        rows = _db.execute("SELECT start, end FROM events WHERE user=?", (user,)).fetchall()
    return [(dt.datetime.fromisoformat(s), dt.datetime.fromisoformat(e)) for s, e in rows]


@mcp.tool(annotations=READ)
def free_slots(days: int = Field(5, ge=1, le=14), duration_minutes: int = Field(30, ge=15, le=120),
               timezone: str = Field("Asia/Karachi", max_length=40), max_slots: int = Field(3, ge=1, le=10),
               ctx: Context | None = None) -> Slots:
    """Free interview slots in working hours (10:00-18:00 local, weekdays), skipping existing holds."""
    user = call_context(ctx)["user_id"]
    tz = ZoneInfo(timezone)
    now = dt.datetime.now(tz)
    busy = _busy(user)
    out: list[Slot] = []
    day = now.date() + dt.timedelta(days=1)
    while len(out) < max_slots and (day - now.date()).days <= days:
        if day.weekday() < 5:
            for hour in (11, 15, 17):
                s = dt.datetime(day.year, day.month, day.day, hour, 0, tzinfo=tz)
                e = s + dt.timedelta(minutes=duration_minutes)
                if all(not (s < be and e > bs) for bs, be in busy):
                    out.append(Slot(start=s.isoformat(), end=e.isoformat(), label=s.strftime("%a %d %b, %H:%M") + f" ({timezone})"))
                    break   # spread slots across days
        day += dt.timedelta(days=1)
    return Slots(timezone=timezone, slots=out)


@mcp.tool(annotations=WRITE)
def create_interview_hold(hold: HoldIn, ctx: Context | None = None) -> Hold:
    """Create a TENTATIVE calendar hold for an interview the client has not confirmed yet. Idempotent per key."""
    c = call_context(ctx)
    s = dt.datetime.fromisoformat(hold.start)
    e = s + dt.timedelta(minutes=hold.duration_minutes)
    with _lock:
        row = _db.execute("SELECT id, start, end, status FROM events WHERE idem=?", (hold.idempotency_key,)).fetchone()
        if row:
            return Hold(event_id=row[0], start=row[1], end=row[2], status=row[3])
        eid = "evt_" + uuid.uuid4().hex[:10]
        _db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)", (eid, c["user_id"], s.isoformat(), e.isoformat(), hold.title, "tentative", hold.idempotency_key))
        _db.commit()
    AUDIT.append(user=c["user_id"], tool="create_interview_hold", args=hold.model_dump(), result={"event_id": eid}, trace_id=c["trace_id"])
    return Hold(event_id=eid, start=s.isoformat(), end=e.isoformat(), status="tentative")


@mcp.tool(annotations=WRITE)
def create_email_draft(draft: EmailDraftIn, ctx: Context | None = None) -> EmailDraft:
    """Create an email DRAFT (never sends). Idempotent per key."""
    c = call_context(ctx)
    with _lock:
        row = _db.execute("SELECT id, subject FROM drafts WHERE idem=?", (draft.idempotency_key,)).fetchone()
        if row:
            return EmailDraft(draft_id=row[0], subject=row[1], status="draft")
        did = "drf_" + uuid.uuid4().hex[:10]
        _db.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?)", (did, c["user_id"], draft.to_name, draft.subject, draft.body,
                                                                 dt.datetime.now().isoformat(), draft.idempotency_key))
        _db.commit()
    AUDIT.append(user=c["user_id"], tool="create_email_draft", args=draft.model_dump(), result={"draft_id": did}, trace_id=c["trace_id"])
    return EmailDraft(draft_id=did, subject=draft.subject, status="draft")


@mcp.resource("workspace://calendar", name="calendar", mime_type="application/json", description="Upcoming holds")
def calendar() -> str:
    with _lock:
        rows = _db.execute("SELECT id, start, end, title, status FROM events ORDER BY start").fetchall()
    return json.dumps([dict(zip(("id", "start", "end", "title", "status"), r)) for r in rows])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8203")))
    a = ap.parse_args()
    if a.http:
        import uvicorn

        from mcp_servers.common import http_app
        uvicorn.run(http_app(mcp), host="0.0.0.0", port=a.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
