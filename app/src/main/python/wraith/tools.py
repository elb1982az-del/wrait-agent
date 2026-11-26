"""Dynamic tool pruning: only send schemas relevant to the current step."""

from __future__ import annotations

from typing import List

SCHEMAS = {
    "nmap": {
        "name": "nmap",
        "purpose": "discover hosts, ports and service versions",
        "example": "nmap -sV -T4 <ip>",
    },
    "nikto": {
        "name": "nikto",
        "purpose": "check a web server for known issues",
        "example": "nikto -h <ip>",
    },
    "hydra": {
        "name": "hydra",
        "purpose": "test login strength with a local wordlist",
        "example": "hydra -l admin -P /usr/share/wordlists/passwords.txt <ip> http",
    },
}


def prune(objective: str, last_output: str = "", step: int = 0) -> List[dict]:
    """Return only the tool schemas that matter for this step."""
    selected = ["nmap"] if step == 0 else []
    lowered_output = last_output.lower()
    lowered_objective = objective.lower()

    if any(token in lowered_output for token in ("80/tcp", "443/tcp", "http", "apache", "nginx")):
        selected.append("nikto")
    if any(token in lowered_objective for token in ("login", "password", "credential", "brute")):
        selected.append("hydra")
    if not selected:
        selected = ["nmap"]
    return [SCHEMAS[name] for name in dict.fromkeys(selected)]
