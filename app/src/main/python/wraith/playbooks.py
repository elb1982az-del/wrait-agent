"""Pre-written attack chains that bypass LLM reasoning tokens."""

from __future__ import annotations

PLAYBOOKS = {
    "quick_web": {
        "keywords": ("web", "http", "website", "apache", "nginx"),
        "steps": [
            "nmap -sV -T4 {target}",
            "nikto -h {target}",
        ],
    },
    "host_discovery": {
        "keywords": ("host", "discover", "scan", "port"),
        "steps": [
            "nmap -sS -T4 {target}",
        ],
    },
    "login_test": {
        "keywords": ("login", "password", "credential"),
        "steps": [
            "nmap -sV -T4 {target}",
            "hydra -l admin -P /usr/share/wordlists/passwords.txt {target} http",
        ],
    },
}


def match(objective: str):
    """Return ``(name, steps)`` for the first matching playbook."""
    lowered = objective.lower()
    for name, playbook in PLAYBOOKS.items():
        if any(keyword in lowered for keyword in playbook["keywords"]):
            return name, list(playbook["steps"])
    return None, []
