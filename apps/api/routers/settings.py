"""Settings: autonomy, budgets, saved searches, connected accounts and the memory viewer
(the user can see and delete everything GigBid has learned)."""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import and_, delete, select, update

from apps.api.auth.users import CurrentUser
from apps.api.schemas.models import Accepted, MemoryItem, SavedSearch, SettingsModel
from common.db import engine, saved_searches, settings
from worker.engine import Engine

router = APIRouter(prefix="/api/settings", tags=["settings"])
MEMORY_NS = ("style", "style_candidates", "outcome")


@router.get("", response_model=SettingsModel)
def get_settings(user=CurrentUser):
    with engine().connect() as c:
        row = c.execute(select(settings.c.data).where(settings.c.user_id == user["id"])).first()
    return SettingsModel(**{k: v for k, v in (row[0] if row else {}).items() if k in SettingsModel.model_fields})


@router.put("", response_model=SettingsModel)
def put_settings(body: SettingsModel, user=CurrentUser):
    with engine().begin() as c:
        row = c.execute(select(settings.c.data).where(settings.c.user_id == user["id"])).first()
        c.execute(update(settings).where(settings.c.user_id == user["id"]).values(data={**(row[0] if row else {}), **body.model_dump()}))
    return body


@router.get("/searches", response_model=list[SavedSearch])
def searches(user=CurrentUser):
    with engine().connect() as c:
        return [SavedSearch(**{k: r[k] for k in SavedSearch.model_fields}) for r in
                c.execute(select(saved_searches).where(saved_searches.c.user_id == user["id"])).mappings()]


@router.post("/searches", response_model=SavedSearch)
def add_search(body: SavedSearch, user=CurrentUser):
    sid = "ss_" + uuid.uuid4().hex[:8]
    with engine().begin() as c:
        c.execute(saved_searches.insert().values(id=sid, user_id=user["id"], query=body.query, category=body.category, skills=body.skills,
                                                 interval_minutes=body.interval_minutes, next_run_at=time.time(), enabled=body.enabled))
    return body.model_copy(update={"id": sid})


@router.delete("/searches/{sid}", response_model=Accepted)
def del_search(sid: str, user=CurrentUser):
    with engine().begin() as c:
        c.execute(delete(saved_searches).where(and_(saved_searches.c.id == sid, saved_searches.c.user_id == user["id"])))
    return Accepted(queued=False, message="deleted")


@router.get("/memory", response_model=list[MemoryItem])
async def memory(user=CurrentUser):
    store = (await Engine.get()).store
    out = []
    for ns in MEMORY_NS:
        for it in await store.asearch((ns, user["id"]), limit=200):
            out.append(MemoryItem(namespace=ns, key=it.key, value=it.value))
    return out


@router.delete("/memory/{namespace}/{key:path}", response_model=Accepted)
async def forget(namespace: str, key: str, user=CurrentUser):
    if namespace not in MEMORY_NS:
        raise HTTPException(422, "unknown memory namespace")
    store = (await Engine.get()).store
    await store.adelete((namespace, user["id"]), key)
    if namespace == "style":   # forgetting a rule also forgets its evidence, or it would be re-promoted
        await store.adelete(("style_candidates", user["id"]), key)
    return Accepted(queued=False, message=f"forgot {namespace}/{key}")
