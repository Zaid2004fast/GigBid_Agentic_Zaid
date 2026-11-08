"""OAuth 2.1 (authorization code + PKCE) for the official Upwork MCP server.

Flow (per the MCP authorization spec):
 1. discover the protected-resource metadata of https://mcp.upwork.com/mcp and its
    authorization server metadata (/.well-known/oauth-authorization-server)
 2. dynamic client registration if no UPWORK_CLIENT_ID is configured
 3. redirect the user to the authorization endpoint with S256 PKCE + state
 4. callback exchanges the code; tokens are stored ENCRYPTED per user (never logged)
 5. refresh_tokens() renews them before expiry (used by the live adapter)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlparse

import httpx
from sqlalchemy import select

from agent.config import cfg
from common.crypto import decrypt, encrypt
from common.db import engine, oauth_tokens

_PENDING: dict[str, dict] = {}   # state -> {verifier, user_id, ts}; short-lived


async def _metadata() -> dict:
    mcp_url = cfg("marketplace.upwork_mcp_url")
    origin = "{0.scheme}://{0.netloc}".format(urlparse(mcp_url))
    async with httpx.AsyncClient(timeout=15) as h:
        auth_server = origin
        try:
            pr = await h.get(f"{origin}/.well-known/oauth-protected-resource")
            if pr.status_code == 200 and pr.json().get("authorization_servers"):
                auth_server = pr.json()["authorization_servers"][0].rstrip("/")
        except httpx.HTTPError:
            pass
        r = await h.get(f"{auth_server}/.well-known/oauth-authorization-server")
        r.raise_for_status()
        return r.json()


async def _client_id(meta: dict, redirect_uri: str) -> tuple[str, str | None]:
    if os.getenv("UPWORK_CLIENT_ID"):
        return os.environ["UPWORK_CLIENT_ID"], os.getenv("UPWORK_CLIENT_SECRET")
    reg = meta.get("registration_endpoint")
    if not reg:
        raise RuntimeError("Upwork authorization server has no dynamic registration; set UPWORK_CLIENT_ID")
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.post(reg, json={"client_name": "GigBid", "redirect_uris": [redirect_uri], "grant_types": ["authorization_code", "refresh_token"],
                                    "response_types": ["code"], "token_endpoint_auth_method": "none"})
        r.raise_for_status()
        return r.json()["client_id"], None


async def start(user_id: str, redirect_uri: str) -> str:
    meta = await _metadata()
    cid, _ = await _client_id(meta, redirect_uri)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    _PENDING[state] = {"verifier": verifier, "user_id": user_id, "ts": time.time(), "client_id": cid, "redirect_uri": redirect_uri,
                       "token_endpoint": meta["token_endpoint"]}
    q = {"response_type": "code", "client_id": cid, "redirect_uri": redirect_uri, "code_challenge": challenge,
         "code_challenge_method": "S256", "state": state, "resource": cfg("marketplace.upwork_mcp_url")}
    return f"{meta['authorization_endpoint']}?{urlencode(q)}"


def _store(user_id: str, tok: dict) -> None:
    exp = time.time() + int(tok.get("expires_in", 3600))
    ct = encrypt(json.dumps(tok))
    with engine().begin() as c:
        if c.execute(select(oauth_tokens.c.user_id).where((oauth_tokens.c.user_id == user_id) & (oauth_tokens.c.provider == "upwork"))).first():
            c.execute(oauth_tokens.update().where((oauth_tokens.c.user_id == user_id) & (oauth_tokens.c.provider == "upwork"))
                      .values(ciphertext=ct, expires_at=exp, updated_at=time.time()))
        else:
            c.execute(oauth_tokens.insert().values(user_id=user_id, provider="upwork", ciphertext=ct, expires_at=exp, updated_at=time.time()))


async def callback(code: str, state: str) -> str:
    p = _PENDING.pop(state, None)
    if not p or time.time() - p["ts"] > 600:
        raise ValueError("invalid or expired OAuth state")
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": p["redirect_uri"], "client_id": p["client_id"],
            "code_verifier": p["verifier"], "resource": cfg("marketplace.upwork_mcp_url")}
    if os.getenv("UPWORK_CLIENT_SECRET"):
        data["client_secret"] = os.environ["UPWORK_CLIENT_SECRET"]
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.post(p["token_endpoint"], data=data)
        r.raise_for_status()
        tok = r.json()
    tok["_client_id"], tok["_token_endpoint"] = p["client_id"], p["token_endpoint"]
    _store(p["user_id"], tok)
    return p["user_id"]


async def refresh_tokens(user_id: str, tok: dict) -> dict:
    data = {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": tok.get("_client_id", os.getenv("UPWORK_CLIENT_ID", ""))}
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.post(tok["_token_endpoint"], data=data)
        r.raise_for_status()
        new = {**tok, **r.json()}
    _store(user_id, new)
    return new


def connected(user_id: str, provider: str = "upwork") -> bool:
    with engine().connect() as c:
        return bool(c.execute(select(oauth_tokens.c.user_id).where((oauth_tokens.c.user_id == user_id) & (oauth_tokens.c.provider == provider))).first())


def store_marketplace_token(user_id: str, provider: str, token: str) -> None:
    ct = encrypt(token)
    with engine().begin() as c:
        c.execute(oauth_tokens.delete().where((oauth_tokens.c.user_id == user_id) & (oauth_tokens.c.provider == provider)))
        c.execute(oauth_tokens.insert().values(user_id=user_id, provider=provider, ciphertext=ct, expires_at=None, updated_at=time.time()))


def peek(user_id: str, provider: str) -> bool:
    with engine().connect() as c:
        row = c.execute(select(oauth_tokens.c.ciphertext).where((oauth_tokens.c.user_id == user_id) & (oauth_tokens.c.provider == provider))).first()
    if not row:
        return False
    decrypt(row[0])   # raises if the key rotated
    return True
