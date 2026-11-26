"""Command allowlist and scope validator.

Nothing here executes commands. Every generated command must pass this gate
before the subprocess bridge is allowed to run it.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shlex
from typing import Iterable, List, Tuple

from .scope import is_allowed

ALLOWED_TOOLS = {"nmap", "nikto", "hydra"}
BLOCK_FRAGMENTS = (
    "rm -rf", "mkfs", "dd ", "sudo ", "su ", "chmod ", "chown ",
    "shutdown", "reboot", "curl ", "wget ", "python", "bash ", "sh ",
    ";", "|", "&", "`", "$(", "&&", "||", ">", "<", "\n", "../",
)
SAFE_PATH_PREFIXES = ("/usr/share/", "/usr/bin/", "/system/bin/", "/sdcard/Download/wraith/")
IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def _extract_targets(argv: List[str]) -> List[str]:
    targets: List[str] = []
    for token in argv:
        candidate = token.split("=", 1)[-1]
        if IP_RE.match(candidate):
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            targets.append(candidate)
    return targets


def validate(command: str, networks: Iterable[ipaddress._BaseNetwork]) -> Tuple[bool, str, List[str], List[str]]:
    """Validate a generated command.

    Returns ``(ok, reason, argv, targets)``.
    """
    raw = command.strip()
    if not raw:
        return False, "empty command", [], []
    lowered = raw.lower()
    for fragment in BLOCK_FRAGMENTS:
        if fragment in lowered:
            return False, f"blocked pattern: {fragment.strip()}", [], []

    try:
        argv = shlex.split(raw)
    except ValueError as exc:
        return False, f"cannot parse command: {exc}", [], []
    if not argv:
        return False, "empty command", [], []

    tool = os.path.basename(argv[0])
    if tool not in ALLOWED_TOOLS:
        return False, f"tool not allowlisted: {tool}", [], []

    for token in argv[1:]:
        if "/" in token and not token.startswith("-"):
            if not any(token.startswith(prefix) for prefix in SAFE_PATH_PREFIXES):
                return False, f"unsafe path: {token}", [], []

    targets = _extract_targets(argv[1:])
    if not targets:
        return False, "no literal IP target in scope format", argv, []
    for target in targets:
        if not is_allowed(target, networks):
            return False, f"target outside scope: {target}", argv, targets

    return True, "allowed", argv, targets


def shutil_which_missing(tool: str) -> bool:
    """Use shutil.which but keep this module easy to unit-test."""
    import shutil
    return shutil.which(tool) is None
