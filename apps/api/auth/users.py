"""Users, password hashing (bcrypt) and sessions (JWT in an httpOnly cookie; Bearer also accepted)."""
from __future__ import annotations

import os
import time
import uuid

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from common.db import engine, saved_searches, settings, users

SECRET = os.getenv("SECRET_KEY", "dev-only-secret-change-me")
COOKIE = "gigbid_session"
TTL = 7 * 86400

PERSONA_DEFAULTS = {
    "aiml": {"floor_hourly": 45, "min_fixed": 400, "category": "AI & Machine Learning"},
    "web": {"floor_hourly": 35, "min_fixed": 300, "category": "Web Development"},
    "data": {"floor_hourly": 30, "min_fixed": 250, "category": "Data Analytics"},
}


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def make_token(uid: str) -> str:
    return jwt.encode({"sub": uid, "exp": int(time.time()) + TTL}, SECRET, algorithm="HS256")


def create_user(email: str, password: str, name: str, persona: str | None, reviewer: bool = False) -> str:
    uid = "u_" + uuid.uuid4().hex[:10]
    with engine().begin() as c:
        c.execute(users.insert().values(id=uid, email=email.lower(), password_hash=hash_pw(password), name=name, persona=persona,
                                        created_at=time.time(), is_reviewer=reviewer))
        d = PERSONA_DEFAULTS.get(persona or "aiml", PERSONA_DEFAULTS["aiml"])
        c.execute(settings.insert().values(user_id=uid, data={
            "floor_hourly": d["floor_hourly"], "min_fixed": d["min_fixed"], "weekly_connects": 120, "autonomy": "suggest",
            "pacing": True, "strategy": "evidence_first", "hours_per_week": 30, "timezone": "Asia/Karachi",
            "onboarded": False, "marketplace": "gigsim"}))
        c.execute(saved_searches.insert().values(id="ss_" + uuid.uuid4().hex[:8], user_id=uid, query="", category=d["category"],
                                                 skills="", interval_minutes=30, next_run_at=time.time(), last_seen_posted_at=None,
                                                 enabled=True))
    return uid


def ensure_reviewer() -> None:
    """Preloaded reviewer login (credentials from env, never committed)."""
    email = os.getenv("REVIEWER_EMAIL", "reviewer@gigbid.dev")
    pw = os.getenv("REVIEWER_PASSWORD", "change-me-in-env")
    with engine().connect() as c:
        if c.execute(select(users.c.id).where(users.c.email == email)).first():
            return
    uid = create_user(email, pw, "Reviewer", os.getenv("REVIEWER_PERSONA", "aiml"), reviewer=True)
    with engine().begin() as c:
        row = c.execute(select(settings.c.data).where(settings.c.user_id == uid)).first()
        c.execute(settings.update().where(settings.c.user_id == uid).values(data={**row[0], "onboarded": True}))


def current_user(request: Request) -> dict:
    tok = request.cookies.get(COOKIE) or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not tok:
        raise HTTPException(401, "not signed in")
    try:
        uid = jwt.decode(tok, SECRET, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "session expired") from None
    with engine().connect() as c:
        row = c.execute(select(users).where(users.c.id == uid)).mappings().first()
    if not row:
        raise HTTPException(401, "unknown user")
    from common.tracing import current_user as cu
    cu.set(uid)
    return dict(row)


CurrentUser = Depends(current_user)
