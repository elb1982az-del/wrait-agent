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

ALLOWED_TOOLS = {
    "nmap", "nikto", "hydra", "chisel", "sqlmap", "responder-ng",
    "subfinder", "httpx", "nuclei", "ffuf",
}
BLOCK_FRAGMENTS = (
    "rm -rf", "mkfs", "dd ", "sudo ", "su ", "chmod ", "chown ",
    "shutdown", "reboot", "curl ", "wget ", "python", "bash ", "sh ",
    "--os-shell", "--os-cmd", "--sql-shell", "--file-write", "--file-read",
    "--dump-all",
    ";", "|", "&", "`", "$(", "&&", "||", ">", "<", "\n", "../",
)
SAFE_PATH_PREFIXES = ("/usr/share/", "/usr/bin/", "/system/bin/", "/sdcard/Download/wraith/")
IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# Responder-NG poisons name resolution on a local network. Keep it inside a
# single in-scope IPv4 interface and refuse modes that affect other hosts or
# weaken authentication. The IP itself is checked by the common scope gate.
RESPONDER_BLOCKED_FLAGS = {
    "-d", "--dhcp", "-D", "--dhcp-dns", "--dhcpv6", "--rdnss", "--dnssl",
    "-b", "--basic", "--lm", "--disable-ess", "-u", "--upstream-proxy",
    "-6", "--externalip6",
}
RESPONDER_IP_FLAGS = {"-i", "--ip", "-e", "--externalip"}
RESPONDER_INTERFACES = {
    "wlan0", "wlan1", "wlan2", "wlan3",
    "eth0", "eth1", "usb0", "usb1",
}


def _validate_responder_flags(argv: List[str]) -> Tuple[bool, str]:
    """Constrain Responder-NG to non-disruptive, IPv4-only, scoped runs."""
    blocked = {flag.lower() for flag in RESPONDER_BLOCKED_FLAGS}
    long_ip_flags = {"--ip", "--externalip"}
    has_ip = False
    has_interface = False
    for index, token in enumerate(argv[1:], 1):
        name = token.split("=", 1)[0]
        lowered = name.lower()
        if lowered in blocked:
            return False, "responder-ng unsafe flag: {}".format(token)
        is_ip_flag = name in RESPONDER_IP_FLAGS or lowered in long_ip_flags
        if is_ip_flag:
            has_ip = True
            value = token.split("=", 1)[1] if "=" in token else ""
            if not value and index + 1 < len(argv):
                value = argv[index + 1]
            if not value or "://" in value or not IP_RE.match(value):
                return False, "responder-ng target must be a literal IPv4 address"
        if name in ("-I", "--interface") or lowered == "--interface":
            has_interface = True
            value = token.split("=", 1)[1] if "=" in token else ""
            if not value and index + 1 < len(argv):
                value = argv[index + 1]
            if value.upper() == "ALL":
                return False, "responder-ng interface ALL is not allowed"
            if value.lower() not in RESPONDER_INTERFACES:
                return False, "responder-ng interface not allowed: {}".format(value)
    if not has_interface:
        return False, "responder-ng requires an interface (-I wlan0/wlan1/wlan2)"
    if not has_ip:
        return False, "responder-ng requires an in-scope IPv4 target via -i/-e"
    return True, "allowed"


def _extract_targets(argv: List[str]) -> List[str]:
    """Pull literal IPv4 targets from IPs, host:port pairs and URLs."""
    targets: List[str] = []
    for token in argv:
        candidate = token.split("=", 1)[-1]
        if "://" in candidate:
            candidate = candidate.split("://", 1)[1]
        if "@" in candidate:
            candidate = candidate.rsplit("@", 1)[1]
        candidate = candidate.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if ":" in candidate:
            host, _, port = candidate.rpartition(":")
            if port.isdigit():
                candidate = host
        if not IP_RE.match(candidate):
            continue
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
    if tool == "responder-ng":
        flag_ok, flag_reason = _validate_responder_flags(argv)
        if not flag_ok:
            return False, flag_reason, argv, []

    for token in argv[1:]:
        if "/" in token and not token.startswith("-") and "://" not in token:
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
