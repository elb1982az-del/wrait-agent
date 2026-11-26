"""History compression: keep recent turns verbatim, summarize the rest."""

from __future__ import annotations

from typing import List


def compress(history: List[str], keep: int = 4, summary_chars: int = 600) -> str:
    """Return a compact representation of the conversation history."""
    if len(history) <= keep:
        return "\n".join(history)
    older = history[:-keep]
    recent = history[-keep:]
    summary = " | ".join(item.replace("\n", " ")[:160] for item in older)
    if len(summary) > summary_chars:
        summary = summary[:summary_chars] + "...(truncated)"
    return "SUMMARY OF EARLIER STEPS:\n" + summary + "\n\nRECENT STEPS:\n" + "\n".join(recent)
