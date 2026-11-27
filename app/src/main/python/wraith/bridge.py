"""Small synchronous bridge called from Java/Kotlin with Chaquopy.

Java side calls ``configure(baseDir, scopePath, logPath)`` once, then ``run()``
which returns immediately while a Python worker thread does the work.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict

from . import audit, scope
from .core import Agent

_state: Dict[str, object] = {
    "status": "idle",
    "base": None,
    "scope_path": None,
    "log_path": None,
    "stop": None,
    "thread": None,
    "agent": None,
}


def configure(base_dir: str, scope_path: str, log_path: str) -> str:
    """Set paths and prepare the audit database. Returns a status string."""
    os.makedirs(base_dir, exist_ok=True)
    os.environ["HOME"] = base_dir
    os.environ["OPENCODE_RELAY_DIR"] = base_dir
    _state["base"] = base_dir
    _state["scope_path"] = scope_path
    _state["log_path"] = log_path
    _state["stop"] = threading.Event()
    audit.init_db()
    _append("bridge configured: {}".format(base_dir))
    return "ready"


def _append(line: str) -> None:
    path = _state.get("log_path")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line.rstrip() + "\n")
            handle.flush()
    except OSError:
        pass


def run(objective: str, dry_run: bool) -> str:
    """Start an agent run. Non-blocking."""
    if _state["status"] == "running":
        _append("[warn] agent already running")
        return "already_running"

    def sink(line: str) -> None:
        _append(line)

    networks, errors = scope.load_scope(str(_state["scope_path"]))
    for error in errors:
        sink("[warn] " + error)
    _state["stop"] = threading.Event()
    agent = Agent(
        objective=str(objective),
        networks=networks,
        base_dir=str(_state["base"]),
        dry_run=bool(dry_run),
        log=sink,
        stop_event=_state["stop"],
    )
    _state["agent"] = agent
    _state["status"] = "running"

    def worker() -> None:
        try:
            agent.run()
        except Exception as exc:
            sink("[error] agent crashed: {}".format(exc))
            audit.log({"level": "error", "detail": {"error": str(exc)}})
        finally:
            _state["status"] = "idle"

    _state["thread"] = threading.Thread(target=worker, name="wraith-agent", daemon=True)
    _state["thread"].start()
    return "started"


def stop() -> str:
    event = _state.get("stop")
    if event is not None:
        event.set()
    try:
        base = str(_state.get("base") or "")
        if base:
            path = os.path.join(base, "bridge_stop.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"stop": True}, handle)
    except OSError:
        pass
    _append("[info] stop signal sent")
    return "stopping"


def status() -> str:
    return str(_state["status"])


def recent(limit: int = 200) -> str:
    rows = audit.recent(limit)
    lines = []
    for row in reversed(rows):
        lines.append("{} [{}] {}".format(
            row.get("command") or "", row.get("level", ""), row.get("detail", "")[:180]
        ))
    return "\n".join(lines)
