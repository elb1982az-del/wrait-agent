"""Offline CVE matching for service banners, no LLM tokens required."""

from __future__ import annotations

import json
import os
from typing import List


def _database() -> List[dict]:
    path = os.path.join(os.path.dirname(__file__), "data", "cve_offline.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return []


def match(text: str) -> List[dict]:
    lowered = text.lower()
    hits = []
    for entry in _database():
        pattern = entry.get("pattern", "").lower()
        if pattern and pattern in lowered:
            hits.append(entry)
    return hits
