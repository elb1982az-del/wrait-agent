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
    "chisel": {
        "name": "chisel",
        "purpose": "create an authorized TCP tunnel or forward",
        "example": "chisel client <ip>:8080 R:1080:socks",
    },
    "sqlmap": {
        "name": "sqlmap",
        "purpose": "test a web application for SQL injection",
        "example": "sqlmap -u http://<ip> --batch --level=1",
    },
    "responder-ng": {
        "name": "responder-ng",
        "purpose": "passively observe or safely test LLMNR/NBT-NS/mDNS on an in-scope interface",
        "example": "responder-ng -I wlan1 -i <ip> -A -v",
    },
    "subfinder": {
        "name": "subfinder",
        "purpose": "enumerate subdomains for an in-scope target",
        "example": "subfinder -d <ip>",
    },
    "httpx": {
        "name": "httpx",
        "purpose": "probe an in-scope host for live HTTP services",
        "example": "httpx -u http://<ip>",
    },
    "nuclei": {
        "name": "nuclei",
        "purpose": "run offline vulnerability templates against an in-scope target",
        "example": "nuclei -u http://<ip>",
    },
    "ffuf": {
        "name": "ffuf",
        "purpose": "fuzz paths on an in-scope web server with a local wordlist",
        "example": "ffuf -u http://<ip>/FUZZ -w /usr/share/wordlists/rockyou.txt",
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
    if any(token in lowered_objective for token in ("sql", "sqli", "injection", "database")):
        selected.append("sqlmap")
    if any(token in lowered_objective for token in ("tunnel", "proxy", "pivot", "forward", "chisel")):
        selected.append("chisel")
    if any(token in lowered_objective for token in ("responder", "llmnr", "nbt-ns", "nbtns", "mdns", "name resolution")):
        selected.append("responder-ng")
    if any(token in lowered_objective for token in ("subdomain", "subfinder", "enumerate domain")):
        selected.append("subfinder")
    if any(token in lowered_objective for token in ("probe", "httpx", "live http")):
        selected.append("httpx")
    if any(token in lowered_objective for token in ("nuclei", "vulnerability template", "cve scan")):
        selected.append("nuclei")
    if any(token in lowered_objective for token in ("ffuf", "fuzz", "directory brute")):
        selected.append("ffuf")
    if not selected:
        selected = ["nmap"]
    return [SCHEMAS[name] for name in dict.fromkeys(selected)]
