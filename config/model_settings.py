import json
import os
import fnmatch
import copy
from typing import Dict, Any, List
from utils.logging_setup import get_logger

logger = get_logger()

MODEL_SETTINGS_FILE = "data/model_settings.json"

DEFAULT_MODEL_SETTINGS = {
    "defaults": {
        "multimodal": False,
    },
    "patterns": [
        {
            "match": ["*gemini*", "*gemma*", "*mistral*"],
            "settings": {"multimodal": True},
        }
    ],
    "models": {},
    "resolved": {},
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


class ModelSettingsManager:
    def __init__(self):
        self._settings: Dict[str, Any] = {}
        self._dirty = False
        self.load()

    def load(self):
        try:
            os.makedirs(os.path.dirname(MODEL_SETTINGS_FILE), exist_ok=True)
            if os.path.exists(MODEL_SETTINGS_FILE):
                with open(MODEL_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    self._settings = json.load(f)
                for key, value in DEFAULT_MODEL_SETTINGS.items():
                    if key not in self._settings:
                        self._settings[key] = copy.deepcopy(value)
            else:
                self._settings = copy.deepcopy(DEFAULT_MODEL_SETTINGS)
                self._save()
            self._dirty = False
        except Exception as e:
            logger.error(f"Error loading model settings: {e}")
            self._settings = copy.deepcopy(DEFAULT_MODEL_SETTINGS)
            self._dirty = False

    def save(self):
        if self._dirty:
            self._save()
            self._dirty = False

    def _rebuild_resolved(self):
        resolved = {}
        for model_name in self._settings.get("models", {}):
            resolved[model_name] = self.resolve_settings(model_name)
        self._settings["resolved"] = resolved

    def _save(self):
        try:
            os.makedirs(os.path.dirname(MODEL_SETTINGS_FILE), exist_ok=True)
            self._rebuild_resolved()
            with open(MODEL_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving model settings: {e}")

    @property
    def defaults(self) -> Dict[str, Any]:
        return self._settings.get("defaults", {})

    @defaults.setter
    def defaults(self, value: Dict[str, Any]):
        self._settings["defaults"] = value
        self._dirty = True

    @property
    def patterns(self) -> List[Dict[str, Any]]:
        return self._settings.get("patterns", [])

    @patterns.setter
    def patterns(self, value: List[Dict[str, Any]]):
        self._settings["patterns"] = value
        self._dirty = True

    @property
    def models(self) -> Dict[str, Dict[str, Any]]:
        return self._settings.get("models", {})

    @models.setter
    def models(self, value: Dict[str, Dict[str, Any]]):
        self._settings["models"] = value
        self._dirty = True

    def _pattern_matches(self, model_name: str, pattern: str) -> bool:
        return fnmatch.fnmatch(model_name.lower(), pattern.lower())

    def resolve_settings(self, model_name: str) -> Dict[str, Any]:
        result = copy.deepcopy(self.defaults)

        for pattern_rule in self.patterns:
            match_list = pattern_rule.get("match", [])
            if any(self._pattern_matches(model_name, p) for p in match_list):
                result = _deep_merge(result, pattern_rule.get("settings", {}))

        exact = self.models.get(model_name)
        if exact:
            result = _deep_merge(result, exact)

        return result

    def is_multimodal(self, model_name: str) -> bool:
        return self.resolve_settings(model_name).get("multimodal", False)

    def register_model(self, model_name: str):
        if model_name in self.models:
            return
        self.models[model_name] = {}
        self._dirty = True
        logger.debug(f"Auto-registered model '{model_name}'")

    def register_all_configured_models(self, llm_config: Dict[str, Any]):
        seen = set()
        global_models = llm_config.get("models", {})
        for model_name in global_models.values():
            if model_name and model_name not in seen:
                seen.add(model_name)
                self.register_model(model_name)

        for server_config in llm_config.get("servers", {}).values():
            if not isinstance(server_config, dict):
                continue
            for model_name in server_config.get("models", {}).values():
                if model_name and model_name not in seen:
                    seen.add(model_name)
                    self.register_model(model_name)
            for model_name in server_config.get("reasoning_budgets", {}).keys():
                if model_name and model_name not in seen:
                    seen.add(model_name)
                    self.register_model(model_name)

        self.save()

    def migrate_from_whitelist(self, whitelist: List[str]):
        if self.patterns:
            return

        if not whitelist:
            return

        match_list = [f"*{keyword}*" for keyword in whitelist]
        self.patterns = [
            {
                "match": match_list,
                "settings": {"multimodal": True},
            }
        ]
        logger.info(
            f"Migrated multimodal whitelist {whitelist} -> pattern {match_list}"
        )
        self._dirty = True


model_settings = ModelSettingsManager()
