"""Minimal YAML scope loader for Wraith.

Only the simple ``allowed:`` list format is supported, which keeps the APK free
of third-party Python packages while still giving the safety layer a real
configuration file.
"""

from __future__ import annotations

import ipaddress
import os
import re
from typing import Iterable, List, Tuple


def default_scope_text() -> str:
    path = os.path.join(os.path.dirname(__file__), "data", "default_scope.yaml")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return "allowed:\n  - 192.168.0.0/24\n"


def _looks_like_network(token: str) -> bool:
    """Cheap pre-filter so prose in a scope field is not reported as an IP."""
    return any(ch.isdigit() for ch in token) and any(ch in token for ch in ".:/")


def _tokenize(value: str) -> List[str]:
    """Split an inline value on commas, semicolons, or whitespace."""
    cleaned = value.strip().strip("[]")
    return [item.strip("\"'[],;") for item in re.split(r"[\s,;]+", cleaned) if item.strip()]


def parse_scope(text: str) -> Tuple[List[ipaddress._BaseNetwork], List[str]]:
    """Parse YAML lists, inline lists, or plain IPs/CIDRs into networks."""
    networks: List[ipaddress._BaseNetwork] = []
    errors: List[str] = []
    section: str | None = None

    def add(value: str) -> None:
        value = value.strip().strip("\"'[]")
        if not value:
            return
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError as exc:
            errors.append(f"invalid scope entry {value!r}: {exc}")

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        header = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", stripped)
        if header and not line.startswith((" ", "\t")):
            section = header.group(1).lower()
            if section == "allowed":
                inline = header.group(2).strip()
                if inline:
                    for token in _tokenize(inline):
                        add(token)
            continue

        if stripped.startswith("-"):
            if section in (None, "allowed"):
                for token in _tokenize(stripped[1:]):
                    add(token)
            continue

        # Plain scope fields: one or more IPs/CIDRs on a line.
        for token in _tokenize(stripped):
            if _looks_like_network(token):
                add(token)

    return networks, errors


def load_scope(path: str) -> Tuple[List[ipaddress._BaseNetwork], List[str]]:
    """Load a scope file from disk, falling back to the bundled default."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = default_scope_text()
    return parse_scope(text)


def target_from_scope(networks: Iterable[ipaddress._BaseNetwork]) -> str | None:
    """Pick a sensible first target from the allowed networks."""
    for network in networks:
        if network.version == 4:
            if network.num_addresses > 2:
                return str(network.network_address + 1)
            return str(network.network_address)
    for network in networks:
        return str(network.network_address)
    return None


def is_allowed(target: str, networks: Iterable[ipaddress._BaseNetwork]) -> bool:
    """Return True when a literal IP is inside the configured scope."""
    try:
        address = ipaddress.ip_address(target.strip())
    except ValueError:
        return False
    return any(address in network for network in networks)
