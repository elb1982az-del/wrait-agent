"""Tiny HTTP client for the free OpenCode model pool on the device."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class OpenCodeError(RuntimeError):
    pass


class OpenCodeClient:
    def __init__(self, base_url: str = "http://127.0.0.1:49374",
                 model_id: str = "opencode/big-pickle", timeout: int = 90):
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise OpenCodeError(f"HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise OpenCodeError(str(exc)) from exc

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
