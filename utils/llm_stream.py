from dataclasses import dataclass
from typing import Any, Dict, Optional


def normalize_reasoning_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "thinking":
                parts.append(item.get("thinking", ""))
        return "".join(parts)
    return ""


@dataclass(frozen=True)
class StreamChunkEvent:
    content_delta: str = ""
    reasoning_delta: str = ""
    finish_reason: Optional[str] = None
    usage: Optional[Any] = None
    error: Optional[str] = None


def parse_chat_completion_stream_chunk(chunk: Dict[str, Any]) -> StreamChunkEvent:
    """Normalize an OpenAI-compatible chat completion stream chunk."""
    if not isinstance(chunk, dict):
        return StreamChunkEvent()

    if "error" in chunk:
        error_message = chunk.get("error", "Unknown error from proxy")
        if isinstance(error_message, dict):
            error_message = error_message.get("message", str(error_message))
        return StreamChunkEvent(error=str(error_message))

    usage = chunk.get("usage") if "usage" in chunk else None
    choices = chunk.get("choices") or []
    if not isinstance(choices, list) or not choices:
        return StreamChunkEvent(usage=usage)

    choice = choices[0]
    if not isinstance(choice, dict):
        return StreamChunkEvent(usage=usage)

    delta = choice.get("delta") or {}
    if not isinstance(delta, dict):
        delta = {}

    content = delta.get("content")
    return StreamChunkEvent(
        content_delta=content if isinstance(content, str) else "",
        reasoning_delta=normalize_reasoning_content(delta.get("reasoning_content")),
        finish_reason=choice.get("finish_reason"),
        usage=usage,
    )
