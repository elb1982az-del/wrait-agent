"""Minimal YAML scope loader for Wraith.

Only the simple ``allowed:`` list format is supported, which keeps the APK free
of third-party Python packages while still giving the safety layer a real
configuration file.
"""

from __future__ import annotations

import ipaddress
import os
from typing import Iterable, List, Tuple


def default_scope_text() -> str:
    path = os.path.join(os.path.dirname(__file__), "data", "default_scope.yaml")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return "allowed:\n  - 192.168.0.0/24\n"


def parse_scope(text: str) -> Tuple[List[ipaddress._BaseNetwork], List[str]]:
    """Parse a scope file into networks plus validation errors."""
    networks: List[ipaddress._BaseNetwork] = []
    errors: List[str] = []
    in_allowed = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if not line.startswith((" ", "\t")):
            in_allowed = stripped == "allowed:"
            continue
        if not in_allowed or not stripped.startswith("-"):
            continue
        value = stripped[1:].strip().strip('"').strip("'")
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError as exc:
            errors.append(f"invalid scope entry {value!r}: {exc}")
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
