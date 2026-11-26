"""Tiny HTTP client for the free OpenCode model pool on the device."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class OpenCodeError(RuntimeError):
    pass


class OpenCodeClient:
    def __init__(self, base_url: str = "http://127.0.0.1:49374",
                 model_id: str = "opencode/big-pickle", timeout: int = 90,
                 password: Optional[str] = None, auth_file: Optional[str] = None,
                 relay_dir: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout = timeout
        self.username = "opencode"
        self.password = password or os.environ.get("OPENCODE_PASSWORD") or self._read_password(auth_file)
        self.relay_dir = relay_dir or os.environ.get("OPENCODE_RELAY_DIR") or os.environ.get("HOME")

    @staticmethod
    def _read_password(auth_file: Optional[str]) -> Optional[str]:
        home = os.environ.get("HOME", "")
        candidates = [
            auth_file,
            os.path.join(home, "opencode_auth.json") if home else None,
            os.path.join(os.path.expanduser("~"), ".config", "opencode", "service.json"),
        ]
        for path in candidates:
            if not path:
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    value = json.load(handle).get("password")
                if value:
                    return str(value)
            except Exception:
                continue
        return None

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.password:
            token = base64.b64encode(
                f"{self.username}:{self.password}".encode("utf-8")
            ).decode("ascii")
            headers["Authorization"] = "Basic " + token
        return headers

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            direct_error = f"HTTP {exc.code}: {detail}"
        except Exception as exc:
            direct_error = str(exc)

        # Android blocks untrusted_app UID sockets to root-owned localhost ports,
        # even when the listener is in the same network namespace. Fall back to
        # the root bridge's file-based model relay.
        try:
            return self._relay_request(method, path, body)
        except OpenCodeError as relay_exc:
            raise OpenCodeError(f"{direct_error}; model relay: {relay_exc}") from relay_exc

    def _relay_request(self, method: str, path: str, body: Optional[Dict[str, Any]]) -> Any:
        if not self.relay_dir or not os.path.isdir(self.relay_dir):
            raise OpenCodeError("no relay directory")
        request_path = os.path.join(self.relay_dir, "model_request.json")
        response_path = os.path.join(self.relay_dir, "model_response.json")
        tmp_path = request_path + ".tmp"
        rid = "{}-{}".format(os.getpid(), time.time())
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump({"id": rid, "method": method, "path": path, "body": body},
                          handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, request_path)
        except Exception as exc:
            raise OpenCodeError(f"cannot write relay request: {exc}") from exc

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                with open(response_path, "r", encoding="utf-8") as handle:
                    result = json.load(handle)
                if result.get("id") == rid:
                    if result.get("ok"):
                        return result.get("data")
                    raise OpenCodeError(str(result.get("error", "relay failed")))
            except FileNotFoundError:
                pass
            except OpenCodeError:
                raise
            except Exception:
                pass
            time.sleep(0.1)
        raise OpenCodeError("timed out waiting for model relay")

    def create_session(self, title: str = "wraith-agent") -> str:
        provider, model = self._split_model()
        result = self._request(
            "POST", "/api/session",
            {
                "title": title,
                "model": {"id": model, "providerID": provider},
            },
        )
        return result["data"]["id"]

    def _split_model(self):
        if "/" in self.model_id:
            provider, model = self.model_id.split("/", 1)
            return provider, model
        return "opencode", self.model_id

    def messages(self, session_id: str) -> List[Dict[str, Any]]:
        return self._request("GET", f"/api/session/{session_id}/message").get("data", [])

    def prompt(self, session_id: str, text: str) -> str:
        before = {item.get("id") for item in self.messages(session_id)}
        self._request("POST", f"/api/session/{session_id}/prompt", {"text": text})

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            for item in self.messages(session_id):
                if item.get("id") in before or item.get("type") != "assistant":
                    continue
                if "completed" not in item.get("time", {}):
                    continue
                parts = item.get("content", [])
                text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
                if text_parts:
                    return "\n".join(text_parts).strip()
            time.sleep(1)
        raise OpenCodeError("timed out waiting for assistant reply")
