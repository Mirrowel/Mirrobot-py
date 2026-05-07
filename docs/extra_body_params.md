# Extra Body Params System

This document describes the `extra_body_params` system that allows per-channel and per-server custom parameters to be injected into LLM API request bodies.

## Purpose

Different LLM models support different request body parameters that aren't part of the standard OpenAI-compatible API. For example:
- **kimi-k2.5**: `"thinking": {"type": "disabled"}` disables thinking mode
- **Gemini**: `"reasoning_effort": "low"` controls reasoning depth
- **OpenAI o-series**: `"reasoning": {"effort": "low"}`

This system lets server admins configure these model-specific parameters per channel and per server, without needing to change code.

## Data Model

The `extra_body_params` field is a `Dict[str, Dict[str, Any]]` stored as:

```json
{
  "all": {"thinking": {"type": "disabled"}},
  "chat": {"reasoning_effort": "low"},
  "ask": {"temperature": 0.3}
}
```

**Keys** are model type names: `"all"`, `"chat"`, `"ask"`, `"think"`, `"default"`.
- `"all"` applies to every model type.
- A specific type (e.g. `"chat"`) only applies when that type is being used.

**Values** are arbitrary JSON objects that get deep-merged into the API request body.

### Where it lives

| Scope | Storage file | Dataclass | Field |
|-------|-------------|-----------|-------|
| Chatbot channel | `data/chatbot_config.json` | `ChannelChatbotConfig` (`utils/chatbot/models.py:184`) | `extra_body_params` |
| Inline channel/server | `data/inline_response_config.json` | `InlineResponseConfig` (`utils/inline_response.py:35`) | `extra_body_params` |
| Server-level (base layer) | `data/llm_config.json` | N/A — stored under `servers.{guild_id}.extra_body_params` | N/A |

## Resolution (Deep Merge Hierarchy)

The function `resolve_extra_body_params()` in `config/llm_config_manager.py:272` merges params from all layers. **Later layers override earlier ones via deep merge.** For a given `(guild_id, model_type)`:

```
1. Server "all"          → base defaults for the whole server
2. Server {model_type}   → server overrides for that specific model type
3. Channel "all"         → channel-level defaults (overrides server)
4. Channel {model_type}  → channel-specific type override (highest priority)
```

### Deep merge behavior

`deep_merge(base, override)` recursively merges dicts. If a key exists in both and both values are dicts, they're merged recursively. Otherwise the override wins. Source dicts are not mutated (uses `copy.deepcopy`).

Example:
```
Server "all":    {"thinking": {"type": "enabled", "budget": 1000}}
Channel "all":   {"thinking": {"type": "disabled"}}
─────────────────────────────────────────────────
Resolved:        {"thinking": {"type": "disabled", "budget": 1000}}
```

The `budget` key from server is preserved; only `type` was overridden by the channel.

## How params flow into API requests

### `make_llm_request()` — `cogs/llm_commands.py:275`

This is the single entry point for all LLM API calls. It accepts an `extra_body_params: Optional[Dict[str, Dict[str, Any]]]` parameter (line 297).

After building `request_kwargs` (which includes model, messages, temperature, reasoning budget, etc.), the resolved params are applied (lines 371-374):

```python
resolved_ebp = resolve_extra_body_params(
    self.llm_config, guild_id, model_type, channel_params=extra_body_params
)
if resolved_ebp:
    deep_merge(request_kwargs, resolved_ebp)
```

This happens **after** the reasoning budget logic, so extra_body_params can override even reasoning settings.

### Call sites

| Caller | File | Line | `model_type` | Source of `extra_body_params` |
|--------|------|------|-------------|------------------------------|
| Chatbot mode | `core/bot.py` | 1002 | `"chat"` | `channel_config.extra_body_params` |
| Inline (streaming) | `cogs/inline_response.py` | 1308 | `config.model_type` | `config.extra_body_params` |
| Inline (non-streaming) | `cogs/inline_response.py` | 1335 | `config.model_type` | `config.extra_body_params` |
| `/ask` command | `cogs/llm_commands.py` | ~1210 | `"ask"` | `None` (not passed) |
| `/think` command | `cogs/llm_commands.py` | ~1287 | `"think"` | `None` (not passed) |

**Note:** The `/ask` and `/think` slash commands do NOT currently pass channel-level extra_body_params. They go through `make_llm_request()` without the parameter, so they still get server-level params from the resolve function (which reads `llm_config` directly), but no channel-level params.

## Commands

### Chatbot channels
```
!chatbot_extra_params {"thinking":{"type":"disabled"}}           # all types
!chatbot_extra_params chat {"reasoning_effort":"low"}            # chat only
!chatbot_extra_params clear                                      # clear all
!chatbot_extra_params clear chat                                 # clear chat-specific
```
Requires: `chatbot_config` permission. Chatbot must be enabled in the channel.

### Server-level
```
!server_extra_params {"thinking":{"type":"disabled"}}            # all types
!server_extra_params chat {"reasoning_effort":"low"}             # chat only
!server_extra_params clear                                       # clear all server params
!server_extra_params clear chat                                  # clear chat-specific
```
Requires: `manage_guild` permission.

### Inline responses
```
!inline params {"thinking":{"type":"disabled"}}                  # all types, current channel
!inline params chat {"reasoning_effort":"low"}                   # chat type, current channel
!inline params clear                                             # clear all
!inline params clear chat                                        # clear chat-specific
!inline params clear chat #general                              # clear for a specific channel
```
Requires: `manage_guild` permission. Target can be `server`, a #channel, or a channel ID.

### View resolved params
```
!view_extra_params
```
Shows server-level, channel-level, and the final resolved (effective) params for each model type.

## Resilient JSON Parser — `utils/json_utils.py`

All three commands use `parse_params_input()` from `utils/json_utils.py` which auto-corrects common JSON mistakes:

1. **Strips code block fences**: `` ```json ... ``` `` → just the JSON
2. **Single quotes → double quotes**: `{'key': 'val'}` → `{"key": "val"}`
3. **Trailing commas**: `{"a": 1,}` → `{"a": 1}`
4. **Missing outer braces**: `"key": "val"` → `{"key": "val"}`
5. **Missing closing braces**: `{"a": {"b": 1}` → `{"a": {"b": 1}}`
6. **Multi-line input**: Handles copy-paste with newlines

After parsing, it returns the pretty-printed formatted JSON so the user can verify it was interpreted correctly.

### Function signatures

```python
def parse_resilient_json(raw: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Returns (parsed_dict, formatted_json_string) or (None, error_message)"""

def parse_params_input(raw: str) -> Tuple[Optional[str], Optional[Dict[str, Any]], str]:
    """Returns (model_type, parsed_dict, formatted_json) or (None, None, error_message)
    Also splits optional model type prefix: 'chat {"key":"val"}' → ('chat', {'key':'val'}, ...)"""
```

## Key functions in `config/llm_config_manager.py`

| Function | Purpose |
|----------|---------|
| `deep_merge(base, override)` | Recursively merges override into base. Mutates base, deep-copies values from override. |
| `resolve_extra_body_params(llm_config, guild_id, model_type, channel_params)` | Resolves the full hierarchy. Returns merged dict. |
| `save_server_extra_body_params(guild_id, model_type, params)` | Writes to `data/llm_config.json` |
| `clear_server_extra_body_params(guild_id, model_type=None)` | Clears server-level params |
| `get_server_extra_body_params(guild_id)` | Reads server-level params from `llm_config.json` |

## Notes for per-model settings integration

Currently `extra_body_params` is keyed by **model type** (`"chat"`, `"ask"`, `"think"`), not by **model name**. The model type determines which model name is used, but the params are not tied to a specific model identity.

If you want to add per-model-name settings, consider:

1. The `model_type` → `model_name` resolution happens inside `make_llm_request()` via `self.get_model_for_guild(guild_id, model_type)` (around line 340 of `llm_commands.py`). At the point where `resolve_extra_body_params` is called, the model name is already known.

2. You could add a `"models"` key alongside `"all"` in the extra_body_params dict, e.g.:
   ```json
   {
     "all": {"thinking": {"type": "enabled"}},
     "models": {
       "kimi-k2.5": {"thinking": {"type": "disabled"}},
       "deepseek-r1": {"reasoning_effort": "high"}
     }
   }
   ```

3. The resolution order would then become: server "all" → server model_type → server model_name → channel "all" → channel model_type → channel model_name.

4. You'd modify `resolve_extra_body_params()` to accept an optional `model_name` parameter and add the model-name-specific merge steps.

5. The `resolve_extra_body_params` call in `make_llm_request()` (line ~371) already has access to `selected_model` (the resolved model name), so passing it through is straightforward.

## Tests

`tests/test_json_utils.py` — 49 tests covering the resilient JSON parser:
- Code fence stripping
- Single quote → double quote conversion
- Trailing comma removal
- Missing brace wrapping/fixing
- Multi-line input handling
- Model type prefix detection
- Copy-paste scenarios
- Error cases (invalid JSON, arrays, empty input)
