import json
import re
from typing import Any, Dict, Optional, Tuple


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _fix_single_quotes(text: str) -> str:
    in_double = False
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            in_double = not in_double
            result.append(ch)
        elif ch == "'" and not in_double:
            result.append('"')
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def _fix_trailing_commas(text: str) -> str:
    text = re.sub(r"\s*,\s*([}\]])", r"\1", text)
    return text


def _count_braces(text: str) -> Tuple[int, int, int, int]:
    open_curly = 0
    close_curly = 0
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == "{":
                open_curly += 1
            elif ch == "}":
                close_curly += 1
    return open_curly, close_curly, text.count("["), text.count("]")


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def parse_resilient_json(raw: str) -> Tuple[Optional[Dict[str, Any]], str]:
    if not raw or not raw.strip():
        return None, "Empty input."

    text = raw.strip()

    text = _strip_code_fences(text)

    text = _fix_single_quotes(text)
    text = _fix_trailing_commas(text)
    text = text.strip()

    if not text.startswith("{"):
        if text.startswith("["):
            try:
                result = json.loads(text)
                return None, "Extra body parameters must be a JSON object (dict)."
            except (json.JSONDecodeError, ValueError):
                return (
                    None,
                    "Could not parse JSON: input appears to be an array, not an object.",
                )
        text = "{" + text + "}"

    parsed = _try_parse_json(text)
    if parsed is not None:
        return parsed, json.dumps(parsed, indent=2)

    open_c, close_c, open_s, close_s = _count_braces(text)
    missing_curly = open_c - close_c
    missing_square = open_s - close_s
    if missing_curly > 0:
        text += "}" * missing_curly
    if missing_square > 0:
        text += "]" * missing_square

    parsed = _try_parse_json(text)
    if parsed is not None:
        return parsed, json.dumps(parsed, indent=2)

    try:
        result = json.loads(text)
        return result, json.dumps(result, indent=2)
    except json.JSONDecodeError as e:
        return None, f"Could not parse JSON: {e}"


VALID_MODEL_TYPES = ("all", "chat", "ask", "think", "default")


def parse_params_input(
    raw: str,
) -> Tuple[Optional[str], Optional[Dict[str, Any]], str]:
    if not raw or not raw.strip():
        return None, None, "Empty input."

    text = raw.strip()

    target_type = "all"
    json_str = text

    parts = text.split(None, 1)
    if parts and parts[0].lower() in VALID_MODEL_TYPES and len(parts) > 1:
        candidate_json = parts[1].strip()
        if candidate_json and candidate_json[0] in ('"', "'", "{", "[", "`"):
            target_type = parts[0].lower()
            json_str = candidate_json

    parsed, formatted = parse_resilient_json(json_str)
    if parsed is None:
        return None, None, formatted

    if not isinstance(parsed, dict):
        return None, None, "Extra body parameters must be a JSON object (dict)."

    return target_type, parsed, formatted
