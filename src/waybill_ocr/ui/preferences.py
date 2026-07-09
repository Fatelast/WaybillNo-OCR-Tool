import json
import os
from pathlib import Path

APP_CONFIG_DIR_NAME = "WaybillNoOcrTool"
PREFERENCES_FILE_NAME = "preferences.json"


def preferences_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / APP_CONFIG_DIR_NAME / PREFERENCES_FILE_NAME


def load_preferences() -> dict[str, str]:
    path = preferences_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if value}


def save_preferences(preferences: dict[str, str]) -> None:
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8")
