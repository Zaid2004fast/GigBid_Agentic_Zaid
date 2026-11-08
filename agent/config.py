"""Loads agent/config.yaml with ${VAR:-default} environment substitution."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(os.getenv("GIGBID_CONFIG", ROOT / "agent" / "config.yaml"))
_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _sub(text: str) -> str:
    return _VAR.sub(lambda m: os.getenv(m.group(1), m.group(2) or ""), text)


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    return yaml.safe_load(_sub(CONFIG_PATH.read_text(encoding="utf-8")))


def reload_config() -> dict[str, Any]:
    load_config.cache_clear()
    return load_config()


def cfg(path: str, default: Any = None) -> Any:
    """cfg('decision.min_fit_bid') -> value."""
    node: Any = load_config()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def node_model(node: str, profile: str | None = None) -> dict:
    prof = profile or cfg("active_profile", "open")
    p = cfg(f"profiles.{prof}") or cfg("profiles.offline")
    return {**p["default"], **(p.get("nodes", {}).get(node) or {})}
