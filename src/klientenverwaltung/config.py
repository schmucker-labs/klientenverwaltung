import json
import os
from pathlib import Path

_CONFIG_DIR_NAME = "Klientenverwaltung"
_CONFIG_FILENAME = "config.json"
_LAST_KNOWN_DRIVE_PATH_KEY = "last_known_drive_path"


def _config_path() -> Path:
    return Path(os.environ["APPDATA"]) / _CONFIG_DIR_NAME / _CONFIG_FILENAME


def _read_config() -> dict[str, str]:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def get_last_known_drive_path() -> Path | None:
    value = _read_config().get(_LAST_KNOWN_DRIVE_PATH_KEY)
    return Path(value) if value else None


def set_last_known_drive_path(drive_path: Path) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _read_config()
    data[_LAST_KNOWN_DRIVE_PATH_KEY] = str(drive_path)
    path.write_text(json.dumps(data), encoding="utf-8")
