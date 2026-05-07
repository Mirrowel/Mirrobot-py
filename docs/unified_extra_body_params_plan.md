# Unified Extra Body Params Plan

## Overview

Standardize `extra_body_params` across chatbot and inline, adding **per-model** targeting with glob patterns, a unified command syntax with `add`/`show`/`clear` actions, and a `"models"` sub-dict inside the existing `extra_body_params` structure.

---

## 1. Data model

Every `extra_body_params` dict (server-level, chatbot-channel, inline-channel) gets an optional `"models"` key:

```json
{
  "all": {"thinking": {"type": "enabled"}},
  "chat": {"reasoning_effort": "low"},
  "models": {
    "*gemini*": {"reasoning_effort": "low"},
    "logfare/kimi-k2.5": {"thinking": {"type": "disabled"}}
  }
}
```

- Top-level keys (`"all"`, `"chat"`, `"ask"`, `"think"`, `"default"`) — type-keyed params (backward compatible)
- `"models"` sub-dict — keys are either exact model names or glob patterns (`*`, `?`, `[`)

---

## 2. Resolution order

For a request with `(guild_id, model_type, model_name)`, params are deep-merged in this order (each layer overrides previous):

```
Server scope:
  1. server_ebp["all"]
  2. server_ebp[model_type]
  3. server_ebp["models"] patterns matching model_name (top-to-bottom order in dict)
  4. server_ebp["models"][model_name] exact match

Channel scope:
  5. channel_ebp["all"]
  6. channel_ebp[model_type]
  7. channel_ebp["models"] patterns matching model_name
  8. channel_ebp["models"][model_name] exact match
```

---

## 3. Target parsing

A **target** is a string that classifies into one of three categories:

| Target value                           | Category      | Stored under          |
| -------------------------------------- | ------------- | --------------------- |
| `all`, `chat`, `ask`, `think`, `default`         | Type keyword  | `ebp[target]`           |
| Contains `*`, `?`, `[`                       | Model pattern | `ebp["models"][target]` |
| Anything else (e.g. `logfare/kimi-k2.5`) | Exact model   | `ebp["models"][target]` |

**Multi-target**: quoted comma-separated string — `"chat,*gemini*"` → apply to both `chat` type and `*gemini*` pattern. All pieces are classified independently. Mixing types and models is allowed.

---

## 4. Command syntax

Both chatbot and inline get the same command structure. Default action is `add`.

```
!chatbot_params [scope] [action] [target] [json]
!inline params [scope] [action] [target] [json]
```

**Scope** (optional, first positional — auto-detected):
- `server` — server-level
- `#channel` / channel ID — specific channel
- omitted — current channel

**Action** (optional keyword):
- `show` — display params for scope. If target is given, show only that target. No JSON needed.
- `clear` — remove params. If target is given, clear only that target. No JSON needed.
- (omitted / `add`) — set params. Requires target + JSON.

**Target** (optional for `show`/`clear`):
- Type keyword, model name, glob pattern, or quoted multi-target

**JSON** (only for `add`):
- The params to set, parsed by the resilient JSON parser

### Examples

```
!chatbot_params                                    → show current channel + server + resolved
!chatbot_params show                               → same as above
!chatbot_params show server                        → show server params only
!chatbot_params show *gemini*                      → show params matching *gemini* across all scopes
!chatbot_params {"thinking":{}}                    → add for "all", current channel
!chatbot_params server chat {"reasoning":"low"}    → add for "chat" type, server-level
!chatbot_params *gemini* {"reasoning":"low"}       → add for *gemini* pattern, current channel
!chatbot_params server *gemini* {"reasoning":"low"} → add for *gemini*, server-level
!chatbot_params clear                              → clear all, current channel
!chatbot_params clear server                       → clear all, server-level
!chatbot_params clear *gemini*                     → clear *gemini* pattern, current channel
!chatbot_params clear server *gemini*              → clear *gemini* pattern, server-level
!chatbot_params "chat,*gemini*" {"foo":"bar"}      → add to both chat and *gemini*, current channel
```

---

## 5. Argument parsing algorithm

Given the raw input string:

1. **Detect scope** — is first token `server`, a channel mention (`<#id>`), or a numeric channel ID? If yes, consume it. Otherwise scope = current channel.

2. **Detect action** — next token:
   - `show` → show mode, no JSON expected
   - `clear` → clear mode, no JSON expected
   - Anything else → `add` mode (default action)

3. **Detect target** (add/clear mode):
   - If next token starts with `{` → no target specified, target = `"all"`, rest is JSON
   - If next token is a quoted string → multi-target, parse it
   - Otherwise → single target token

4. **Parse JSON** (add mode only) — remaining input passed to resilient JSON parser.

5. **Classify each target piece** — type keyword vs model pattern vs exact model name.

---

## 6. Files to change

| File                         | Change                                                                                                                                                                                                                 |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config/model_settings.py`     | Add `resolve_model_ebp(ebp_dict, model_name, model_type)` — extracts and merges model-keyed entries from a single scope's ebp dict                                                                                       |
| `config/llm_config_manager.py` | Add `model_name` parameter to `resolve_extra_body_params`, delegate model-keyed resolution to the new helper. Update `save_server_extra_body_params` and `clear_server_extra_body_params` to handle `"models"` sub-dict entries. |
| `cogs/llm_commands.py`         | Pass `target_model` to `resolve_extra_body_params` in `make_llm_request`. Rewrite `chatbot_extra_params` + `server_extra_params` → unified `chatbot_params` with new parsing. Update `view_extra_params` (or remove if absorbed).    |
| `cogs/inline_response.py`      | Rewrite `inline params` subcommand with same new target parsing and model support.                                                                                                                                       |
| `utils/json_utils.py`          | Update `parse_params_input` to handle scope detection, action detection, and multi-target classification.                                                                                                                |

---

## 7. Backward compatibility

- Old `extra_body_params` dicts without a `"models"` key work identically — no migration needed.
- Old commands (`!server_extra_params`, `!chatbot_extra_params`) can be kept as aliases or removed.
- The `resolve_extra_body_params` function gains an optional `model_name` parameter — when `None`, model-keyed steps are skipped (identical to old behavior).

---

## 8. Open items (to be addressed during implementation)

- **Chatbot server-level storage**: Chatbot currently has no server-level config for extra_body_params. This will be resolved as part of the broader chatbot/inline config rework.
- **Command naming**: Final command names (`chatbot_params` vs keeping `chatbot_extra_params`) to be decided during the rework.
- **`!view_extra_params`**: Will be removed or converted to an alias once both new commands support `show`.
