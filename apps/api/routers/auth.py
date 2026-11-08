"""Sign-in, onboarding and connected accounts."""
from __future__ import annotations

import os
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update

from apps.api.auth import upwork_oauth
from apps.api.auth.users import COOKIE, TTL, CurrentUser, check_pw, create_user, make_token
from apps.api.schemas.models import Accepted, LoginIn, OnboardingIn, RegisterIn, UserOut
from common.db import engine, saved_searches, settings, users
from rag.corpus import PERSONA_DIR, get_corpus

router = APIRouter(prefix="/api", tags=["auth"])


def _user_out(u: dict) -> UserOut:
    with engine().connect() as c:
        row = c.execute(select(settings.c.data).where(settings.c.user_id == u["id"])).first()
    return UserOut(id=u["id"], email=u["email"], name=u["name"], persona=u["persona"], is_reviewer=bool(u["is_reviewer"]),
                   onboarded=bool((row[0] if row else {}).get("onboarded")))


def _set_cookie(resp: Response, uid: str) -> None:
    resp.set_cookie(COOKIE, make_token(uid), max_age=TTL, httponly=True, samesite="lax", secure=os.getenv("COOKIE_SECURE", "0") == "1")


@router.post("/auth/register", response_model=UserOut)
def register(body: RegisterIn, response: Response):
    with engine().connect() as c:
        if c.execute(select(users.c.id).where(users.c.email == body.email.lower())).first():
            raise HTTPException(409, "email already registered")
    persona = body.persona
    uid = create_user(body.email, body.password, body.name, None if persona == "own" else persona)
    if persona == "own":   # own profile: an isolated, empty portfolio folder for this user
        own = f"u_{uid}"
        (PERSONA_DIR / own / "case_studies").mkdir(parents=True, exist_ok=True)
        (PERSONA_DIR / own / "repos").mkdir(exist_ok=True)
        with engine().begin() as c:
            c.execute(update(users).where(users.c.id == uid).values(persona=own))
    _set_cookie(response, uid)
    with engine().connect() as c:
        return _user_out(dict(c.execute(select(users).where(users.c.id == uid)).mappings().first()))


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginIn, response: Response):
    with engine().connect() as c:
        u = c.execute(select(users).where(users.c.email == body.email.lower())).mappings().first()
    if not u or not check_pw(body.password, u["password_hash"]):
        raise HTTPException(401, "wrong email or password")
    _set_cookie(response, u["id"])
    return _user_out(dict(u))


@router.post("/auth/logout", response_model=Accepted)
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return Accepted(queued=False, message="signed out")


@router.get("/auth/me", response_model=UserOut)
def me(user=CurrentUser):
    return _user_out(user)


@router.post("/onboarding", response_model=UserOut)
def onboarding(body: OnboardingIn, user=CurrentUser):
    persona = user["persona"] if body.persona == "own" and (user["persona"] or "").startswith("u_") else body.persona
    if body.persona == "own" and not (persona or "").startswith("u_"):
        persona = f"u_{user['id']}"
        (PERSONA_DIR / persona / "case_studies").mkdir(parents=True, exist_ok=True)
    with engine().begin() as c:
        c.execute(update(users).where(users.c.id == user["id"]).values(persona=persona))
        row = c.execute(select(settings.c.data).where(settings.c.user_id == user["id"])).first()
        data = {**(row[0] if row else {}), "floor_hourly": body.floor_hourly, "min_fixed": body.min_fixed,
                "weekly_connects": body.weekly_connects, "marketplace": body.marketplace, "onboarded": True}
        c.execute(update(settings).where(settings.c.user_id == user["id"]).values(data=data))
        if body.search_category or body.search_query:
            c.execute(saved_searches.insert().values(id="ss_" + uuid.uuid4().hex[:8], user_id=user["id"], query=body.search_query,
                                                     category=body.search_category, skills="", interval_minutes=30,
                                                     next_run_at=time.time(), enabled=True))
    if body.marketplace == "gigsim" and not persona.startswith("u_"):
        upwork_oauth.store_marketplace_token(user["id"], "gigsim", f"tok_{persona}")
    with engine().connect() as c:
        return _user_out(dict(c.execute(select(users).where(users.c.id == user["id"])).mappings().first()))


@router.post("/portfolio/upload", response_model=Accepted)
async def upload(file: UploadFile, user=CurrentUser):
    """Add a case study (Markdown) - incrementally re-indexed (only new chunks are embedded)."""
    if not file.filename or not file.filename.lower().endswith((".md", ".markdown", ".txt")):
        raise HTTPException(415, "upload a Markdown case study (.md)")
    raw = (await file.read())[:200_000].decode("utf-8", errors="ignore")
    persona = user["persona"] or "aiml"
    up = PERSONA_DIR / persona / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    key = "".join(ch if ch.isalnum() else "-" for ch in file.filename.rsplit(".", 1)[0].lower())[:50]
    if not raw.startswith("---"):
        raw = f"---\nproject: {key}\ntype: case_study\ndate: {time.strftime('%Y-%m')}\n---\n{raw}"
    (up / f"{user['id']}-{key}.md").write_text(raw, encoding="utf-8")
    get_corpus(persona, refresh=True)
    return Accepted(queued=False, message=f"indexed {file.filename}")


@router.get("/accounts/upwork/start")
async def upwork_start(request: Request, user=CurrentUser):
    redirect = str(request.url_for("upwork_callback"))
    try:
        url = await upwork_oauth.start(user["id"], redirect)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Upwork OAuth discovery failed: {e}") from e
    return {"authorize_url": url}


@router.get("/accounts/upwork/callback", name="upwork_callback")
async def upwork_callback(code: str, state: str):
    try:
        await upwork_oauth.callback(code, state)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e
    return RedirectResponse("/settings?connected=upwork")


@router.get("/accounts", response_model=dict)
def accounts(user=CurrentUser):
    return {"gigsim": upwork_oauth.connected(user["id"], "gigsim") or not (user["persona"] or "").startswith("u_"),
            "upwork": upwork_oauth.connected(user["id"], "upwork")}
