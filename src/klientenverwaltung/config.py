import json
import os
from pathlib import Path

_CONFIG_DIR_NAME = "Klientenverwaltung"
_CONFIG_FILENAME = "config.json"
_ERROR_LOG_FILENAME = "error.log"
_LAST_KNOWN_DRIVE_PATH_KEY = "last_known_drive_path"
_BACKUP_FOLDER_PATH_KEY = "backup_folder_path"
_DATA_DRIVE_ID_KEY = "data_drive_id"


def _config_path() -> Path:
    return Path(os.environ["APPDATA"]) / _CONFIG_DIR_NAME / _CONFIG_FILENAME


def error_log_path() -> Path:
    """Where unhandled-exception details get logged (see main._log_and_show_crash).

    Same %APPDATA% folder as config.json - never client data, only
    exception types/code locations/timestamps, so it's fine alongside it.
    """
    return Path(os.environ["APPDATA"]) / _CONFIG_DIR_NAME / _ERROR_LOG_FILENAME


def _read_config() -> dict[str, str]:
    """The settings, or {} if the file is missing or unusable (unreadable,
    no valid JSON, or JSON that is not an object)."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_value(key: str, value: str) -> None:
    """Sets one setting, keeping the others.

    Written to a temporary file that then replaces config.json in one
    step: a crash or power loss mid-write can no longer leave a truncated
    file behind - which would read as {} and silently forget the backup
    folder.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _read_config()
    data[key] = value
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(path)


def get_last_known_drive_path() -> Path | None:
    value = _read_config().get(_LAST_KNOWN_DRIVE_PATH_KEY)
    return Path(value) if value else None


def set_last_known_drive_path(drive_path: Path) -> None:
    _write_value(_LAST_KNOWN_DRIVE_PATH_KEY, str(drive_path))


def get_data_drive_id() -> str | None:
    """The identifier (UUID) of the data drive this laptop works with, if
    one was recorded - tells the real data drive apart from a copy."""
    return _read_config().get(_DATA_DRIVE_ID_KEY) or None


def set_data_drive_id(drive_id: str) -> None:
    _write_value(_DATA_DRIVE_ID_KEY, drive_id)


def get_backup_folder_path() -> Path | None:
    """None means backups are disabled (never set up, or explicitly skipped)."""
    value = _read_config().get(_BACKUP_FOLDER_PATH_KEY)
    return Path(value) if value else None


def set_backup_folder_path(folder_path: Path) -> None:
    _write_value(_BACKUP_FOLDER_PATH_KEY, str(folder_path))


def reset() -> None:
    """Deletes config.json (last known drive, data drive id, backup folder path).

    Used by --reset-settings alongside clearing QSettings, so the app can
    be put back into a fresh-install state for repeatedly testing the
    setup wizard - without this, a stale last_known_drive_path or
    backup_folder_path from a previous install would still linger.
    """
    _config_path().unlink(missing_ok=True)
