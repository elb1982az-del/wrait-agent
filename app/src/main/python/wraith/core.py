"""Wraith execution loop.

Flow: scope -> (playbook | free OpenCode model) -> hard validation -> optional
subprocess execution -> offline CVE hints -> feed output back -> repeat.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from typing import Callable, List, Optional

from . import audit, cve, history, playbooks, scope, tools, validator
from .opencode_client import OpenCodeClient, OpenCodeError

TOOL_PATHS = (
    "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
    "/system/bin", "/system/xbin",
)
NH_TOOL_ROOT = "/data/local/nhsystem/kali-arm64/usr/bin"
BRIDGE_ONLY_TOOLS = {
    "responder-ng", "subfinder", "httpx", "nuclei", "ffuf", "katana", "ligolo-ng",
}

PLAN_PROMPT = """Wraith authorized-planning mode. Target IP: {target}. Scope: {scope}.
Tools available: {schemas}
Return a short numbered list of 1-4 commands using ONLY nmap, nikto, hydra, chisel, sqlmap, responder-ng, subfinder, httpx, nuclei, ffuf, katana or ligolo-ng.
Use the literal target IP. No pipes, redirects, shell operators, wildcards or filenames.
No prose, no markdown fences. One command per line."""

NEXT_PROMPT = """Wraith authorized-planning mode. Objective: {objective}
Target IP: {target}. Scope: {scope}. Tools: {schemas}
Previous steps:
{history}
Reply with EXACTLY ONE command from (nmap, nikto, hydra, chisel, sqlmap, responder-ng, subfinder, httpx, nuclei, ffuf, katana, ligolo-ng) using the literal target IP.
For responder-ng use -I <interface> -i <literal target IP> -A -v and no other flags.
No prose, no fences, no pipes/redirects/shell operators. If the objective is done, reply DONE."""

COMMAND_RE = re.compile(
    r"^(nmap|nikto|hydra|chisel|sqlmap|responder-ng|subfinder|httpx|nuclei|ffuf|katana|ligolo-ng)\s+.+$",
    re.MULTILINE,
)


def extract_commands(text: str, limit: int = 4) -> List[str]:
    """Pull allowlisted commands out of a model reply."""
    found: List[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-").strip()
        line = line.split(".", 1)[-1].strip() if re.match(r"^\d+[\.\)]", line) else line
        line = line.strip("` ").strip()
        if re.match(r"^(nmap|nikto|hydra|chisel|sqlmap|responder-ng|subfinder|httpx|nuclei|ffuf|katana|ligolo-ng)\s+", line):
            found.append(line)
        if len(found) >= limit:
            break
    if not found:
        match = COMMAND_RE.search(text)
        if match:
            found.append(match.group(0).strip())
    return found


class Agent:
    def __init__(self,
                 objective: str,
                 networks,
                 base_dir: str,
                 dry_run: bool = True,
                 log: Optional[Callable[[str], None]] = None,
                 stop_event: Optional[threading.Event] = None,
                 max_steps: int = 8,
                 client: Optional[OpenCodeClient] = None):
        self.objective = objective.strip()
        self.networks = networks
        self.base_dir = base_dir
        self.dry_run = dry_run
        self.log = log
        self.stop_event = stop_event or threading.Event()
        self.max_steps = max_steps
        self.client = client or OpenCodeClient(relay_dir=base_dir)
        self.history_lines: List[str] = []

    def emit(self, level: str, message: str, silent: bool = False, **detail) -> None:
        line = "[{}] {}".format(level.upper(), message)
        if not silent and self.log:
            try:
                self.log(line)
            except Exception:
                pass
        audit.log({
            "level": level,
            "command": detail.get("command"),
            "output": detail.get("output"),
            "allowed": detail.get("allowed"),
            "dry_run": self.dry_run,
            "target": detail.get("target"),
            "detail": detail,
        })

    def run(self) -> None:
        audit.init_db()
        target = scope.target_from_scope(self.networks)
        self.emit("info", "objective: {}".format(self.objective))
        self.emit("info", "scope: {}".format(", ".join(str(n) for n in self.networks)))
        self.emit("info", "dry_run: {}".format(self.dry_run))
        if not target:
            self.emit("error", "scope has no usable IPv4 target")
            return

        playbook_name, steps = playbooks.match(self.objective)
        if steps:
            self.emit("info", "playbook {} selected (no LLM tokens)".format(playbook_name))
            commands = [step.format(target=target) for step in steps]
            if self.dry_run:
                self._preview(commands, target)
            else:
                self._sequential(commands, target)
            return

        if self.dry_run:
            self._llm_plan(target)
        else:
            self._llm_loop(target)

    def _llm_plan(self, target: str) -> None:
        prompt = PLAN_PROMPT.format(
            target=target,
            scope=", ".join(str(n) for n in self.networks),
            schemas=tools.prune(self.objective, step=0),
        )
        try:
            reply = self.client.prompt(self.client.create_session("wraith-dry-run"), prompt)
        except OpenCodeError as exc:
            self.emit("error", "model unavailable: {}".format(exc))
            return
        commands = extract_commands(reply)
        self.emit("info", "model supplied {} planned command(s)".format(len(commands)))
        if not commands:
            self.emit("warn", "no allowlisted command in model reply")
            return
        self._preview(commands, target)

    @staticmethod
    def _chroot_argv(argv: List[str]) -> List[str]:
        if not argv:
            return argv
        return [os.path.join(NH_TOOL_ROOT, os.path.basename(argv[0]))] + argv[1:]

    def _preview(self, commands: List[str], target: str) -> None:
        for index, command in enumerate(commands, 1):
            ok, reason, argv, _ = validator.validate(command, self.networks)
            note = self._tool_note(self._chroot_argv(argv)) if ok else ""
            self.emit(
                "dry-run" if ok else "blocked",
                "{}/{} {} -> {}{}".format(index, len(commands), command, reason, note),
                command=command, allowed=ok, target=target,
            )
        self.emit("info", "dry-run complete; nothing was executed")

    def _llm_loop(self, target: str) -> None:
        try:
            session = self.client.create_session("wraith-agent")
        except OpenCodeError as exc:
            self.emit("error", "model unavailable: {}".format(exc))
            return
        for step in range(1, self.max_steps + 1):
            if self.stop_event.is_set():
                self.emit("info", "stop requested")
                return
            prompt = NEXT_PROMPT.format(
                objective=self.objective,
                target=target,
                scope=", ".join(str(n) for n in self.networks),
                schemas=tools.prune(self.objective, self.history_lines[-1] if self.history_lines else "", step),
                history=history.compress(self.history_lines),
            )
            if step > 1:
                prompt += "\nStep {} of {}. Continue.\n".format(step, self.max_steps)
            try:
                reply = self.client.prompt(session, prompt)
            except OpenCodeError as exc:
                self.emit("error", "model error: {}".format(exc))
                return
            if reply.strip().upper() == "DONE":
                self.emit("info", "model reported objective complete")
                return
            commands = extract_commands(reply, limit=1)
            if not commands:
                self.emit("warn", "no usable command at step {}; stopping".format(step))
                return
            output = self._execute_step(commands[0], target, step)
            if output is None:
                return
            self.history_lines.append("step {}: {}\noutput: {}".format(step, commands[0], output[:800]))

    def _sequential(self, commands: List[str], target: str, from_playbook: bool = False) -> None:
        for step, command in enumerate(commands, 1):
            if self.stop_event.is_set():
                self.emit("info", "stop requested")
                return
            if self._execute_step(command, target, step) is None:
                return

    def _execute_step(self, command: str, target: str, step: int) -> Optional[str]:
        ok, reason, argv, _ = validator.validate(command, self.networks)
        if not ok:
            self.emit("blocked", "step {} rejected: {} :: {}".format(step, reason, command),
                      command=command, allowed=False, target=target)
            return None
        runtime_argv = self._chroot_argv(argv)
        note = self._tool_note(runtime_argv)
        if note:
            self.emit("warn", "step {}:{}".format(step, note), command=command, allowed=True, target=target)
        self.emit("run", "step {}: {}".format(step, command), command=command, allowed=True, target=target)
        output = self._run(runtime_argv, line_callback=self._stream_line)
        if output.startswith("bridge rejected:") or output.startswith("error:"):
            self.emit("error", "step {} failed: {}".format(step, output),
                      command=command, allowed=False, target=target)
            return None
        self.emit("success", "step {} completed".format(step), command=command, allowed=True, target=target)
        self.emit("output", output[:4000], silent=True, command=command,
                  output=output, allowed=True, target=target)
        for hit in cve.match(output):
            self.emit("cve", "{}: {}".format(hit.get("cve", "?"), hit.get("hint", "")))
        return output

    def _tool_note(self, argv: List[str]) -> str:
        """Describe where the tool will be executed from (never blocks)."""
        if not argv:
            return ""
        executable = argv[0]
        if executable.startswith(NH_TOOL_ROOT):
            if os.path.exists(executable):
                return " using Kali chroot tool {}".format(executable)
            tool = os.path.basename(executable)
            if tool in BRIDGE_ONLY_TOOLS:
                return " using root bridge tool {}".format(tool)
            return " {} missing in Kali chroot".format(tool)
        tool = os.path.basename(executable)
        path = ":".join(TOOL_PATHS) + ":" + os.environ.get("PATH", "")
        if shutil.which(tool, path=path) is None:
            return " {} will run through the NetHunter tool bridge".format(tool)
        return ""

    def _stream_line(self, line: str) -> None:
        """Push one streamed bridge line straight to the UI log."""
        if self.log:
            try:
                self.log("[OUT] {}".format(line))
            except Exception:
                pass

    def _bridge_run(self, argv: List[str],
                    line_callback: Optional[Callable[[str], None]] = None) -> str:
        """Request a tool run and stream output lines from the root bridge file."""
        import json
        import time

        request_path = os.path.join(self.base_dir, "bridge_request.json")
        stream_path = os.path.join(self.base_dir, "bridge_stream.txt")
        rid = "{}-{}".format(os.getpid(), time.time())
        request = {"id": rid, "argv": argv}
        tmp_path = request_path + ".tmp"

        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(request, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, request_path)
        except Exception as exc:
            return "error: cannot send bridge request: {}".format(exc)

        collected: List[str] = []
        seen = set()
        deadline = time.time() + 900
        while time.time() < deadline:
            if self.stop_event.is_set():
                try:
                    with open(os.path.join(self.base_dir, "bridge_stop.json"), "w", encoding="utf-8") as handle:
                        handle.write('{"stop":true}')
                except OSError:
                    pass
                return "error: stopped"
            try:
                with open(stream_path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        # Track raw records, not line numbers: the bridge truncates
                        # and rewrites this file for every request.
                        if line in seen:
                            continue
                        seen.add(line)
                        try:
                            item = json.loads(line)
                        except Exception:
                            continue
                        if item.get("id") != rid:
                            continue
                        if not item.get("ok", True):
                            return "bridge rejected: {}".format(item.get("reason", "unknown"))
                        if "line" in item:
                            text = str(item["line"])
                            collected.append(text)
                            if line_callback:
                                line_callback(text)
                        elif item.get("done"):
                            return "\n".join(collected).strip() or "(no output)"
            except FileNotFoundError:
                pass
            except Exception as exc:
                return "error: bridge stream failed: {}".format(exc)
            time.sleep(0.1)
        return "error: bridge timed out"

    def _run(self, argv: List[str],
             line_callback: Optional[Callable[[str], None]] = None) -> str:
        tool = os.path.basename(argv[0]) if argv else ""
        if argv and argv[0].startswith(NH_TOOL_ROOT):
            return self._bridge_run(argv, line_callback)
        path = ":".join(TOOL_PATHS) + ":" + os.environ.get("PATH", "")
        if tool and shutil.which(tool, path=path) is None:
            return self._bridge_run(argv)

        env = dict(os.environ)
        env["PATH"] = ":".join(TOOL_PATHS) + ":" + env.get("PATH", "")
        env["HOME"] = self.base_dir
        env["TERM"] = "xterm"
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, timeout=240, env=env,
                cwd=self.base_dir, errors="replace",
            )
            output = (completed.stdout or "") + (("\n" + completed.stderr) if completed.stderr else "")
            return output.strip() or "(no output, exit {})".format(completed.returncode)
        except subprocess.TimeoutExpired:
            return "error: command timed out after 240s"
        except Exception as exc:
            return "error: {}".format(exc)
