#!/usr/bin/env python3
"""Wraith tool bridge: file-based IPC plus optional localhost HTTP.

The Android app writes bridge_request.json; this root bridge executes the
allowlisted tool and streams each output line into bridge_stream.txt. The app
polls that file, so no socket connectivity from the app is required.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/opt/wrait-agent/app/src/main/python")
from wraith import scope as wscope
from wraith import validator as wval

PORT = 49375
CHROOT_TOOL_ROOT = "/data/local/nhsystem/kali-arm64/usr/bin"
SCOPE_PATHS = (
    "/proc/1/root/data/data/com.wraith.agent/files/scope.yaml",
    "/opt/wrait-agent/app/src/main/python/wraith/data/default_scope.yaml",
)


def app_files():
    for path in ("/data/user/0/com.wraith.agent/files",
                 "/data/data/com.wraith.agent/files",
                 "/proc/1/root/data/data/com.wraith.agent/files"):
        if os.path.isdir(path):
            return path
    return "/data/data/com.wraith.agent/files"


APP_FILES = app_files()
REQUEST = os.path.join(APP_FILES, "bridge_request.json")
STREAM = os.path.join(APP_FILES, "bridge_stream.txt")
MODEL_REQUEST = os.path.join(APP_FILES, "model_request.json")
MODEL_RESPONSE = os.path.join(APP_FILES, "model_response.json")
OPENCODE_URL = "http://127.0.0.1:49374"
OPENCODE_AUTH = "/root/.config/opencode/service.json"


def load_networks():
    for path in SCOPE_PATHS:
        if os.path.exists(path):
            networks, errors = wscope.load_scope(path)
            if networks and not errors:
                return networks
    return wscope.parse_scope("allowed:\n  - 192.168.0.0/24\n")[0]


def emit(out, rid, payload):
    record = dict(payload)
    record["id"] = rid
    out.write(json.dumps(record, separators=(",", ":")) + "\n")
    out.flush()


def run_stream(argv, rid):
    try:
        if not isinstance(argv, list) or not argv:
            raise ValueError("empty argv")
        tool = os.path.basename(str(argv[0]))
        command = " ".join([tool] + [str(a) for a in argv[1:]])
        ok, reason, clean_argv, _ = wval.validate(command, load_networks())
        if not ok:
            raise ValueError(reason)

        executable = os.path.join("/usr/bin", tool)
        if not os.path.exists(executable):
            raise ValueError("tool missing in Kali chroot: " + tool)

        env = dict(os.environ)
        env["PATH"] = CHROOT_TOOL_ROOT + ":/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
        env["HOME"] = "/root"

        with open(STREAM, "w") as out:
            try:
                os.chmod(STREAM, 0o666)
            except OSError:
                pass
            process = subprocess.Popen(
                [executable] + clean_argv[1:], stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, env=env, cwd="/root",
            )
            assert process.stdout is not None
            for raw in process.stdout:
                emit(out, rid, {"ok": True,
                                "line": raw.decode("utf-8", errors="replace").rstrip("\r\n")})
            emit(out, rid, {"ok": True, "done": True, "exit": process.wait()})
    except Exception as exc:
        try:
            with open(STREAM, "a") as out:
                os.chmod(STREAM, 0o666)
                emit(out, rid, {"ok": False, "reason": str(exc)})
        except Exception:
            pass


def _opencode_request(method, path, body):
    with open(OPENCODE_AUTH, "r", encoding="utf-8") as handle:
        password = json.load(handle)["password"]
    token = base64.b64encode(("opencode:" + password).encode("utf-8")).decode("ascii")
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        OPENCODE_URL + path,
        data=data,
        method=method or "GET",
        headers={"Content-Type": "application/json", "Authorization": "Basic " + token},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def run_model(request, rid):
    result = {"id": rid}
    try:
        path = str(request.get("path", ""))
        if not path.startswith("/"):
            raise ValueError("invalid model path")
        result["data"] = _opencode_request(
            str(request.get("method", "GET")).upper(), path, request.get("body"))
        result["ok"] = True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        result["ok"] = False
        result["error"] = "HTTP {}: {}".format(exc.code, detail)
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)

    tmp_path = MODEL_RESPONSE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as out:
            json.dump(result, out, separators=(",", ":"))
            out.flush()
            os.fsync(out.fileno())
        try:
            info = os.stat(MODEL_REQUEST)
            os.chown(tmp_path, info.st_uid, info.st_gid)
        except OSError:
            pass
        try:
            os.chmod(tmp_path, 0o666)
        except OSError:
            pass
        os.replace(tmp_path, MODEL_RESPONSE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def watch_requests():
    last_id = None
    last_model_id = None
    while True:
        try:
            with open(REQUEST, "r", encoding="utf-8") as handle:
                request = json.load(handle)
            rid = request.get("id")
            if rid and rid != last_id:
                last_id = rid
                run_stream(request.get("argv", []), rid)
        except Exception:
            pass
        try:
            with open(MODEL_REQUEST, "r", encoding="utf-8") as handle:
                request = json.load(handle)
            rid = request.get("id")
            if rid and rid != last_model_id:
                last_model_id = rid
                run_model(request, rid)
        except Exception:
            pass
        time.sleep(0.1)


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    ipv6_v6only = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        body = json.dumps({"ok": True, "port": PORT, "streaming": True,
                           "model_relay": True, "app_files": APP_FILES}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    threading.Thread(target=watch_requests, daemon=True).start()
    DualStackServer(("::", PORT), Handler).serve_forever()
