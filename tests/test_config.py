from pathlib import Path

import pytest

from klientenverwaltung import config


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


@pytest.mark.parametrize("content", ["[1, 2]", '"text"', "{kaputt", ""])
def test_an_unusable_config_file_reads_as_empty(content: str) -> None:
    path = config.error_log_path().with_name("config.json")
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")

    assert config.get_backup_folder_path() is None
    assert config.get_last_known_drive_path() is None


def test_settings_survive_each_other_and_leave_no_temporary_file(tmp_path: Path) -> None:
    config.set_backup_folder_path(tmp_path / "Sicherungen")
    config.set_last_known_drive_path(Path("E:/"))

    assert config.get_backup_folder_path() == tmp_path / "Sicherungen"
    assert config.get_last_known_drive_path() == Path("E:/")
    folder = config.error_log_path().parent
    assert [path.name for path in folder.iterdir()] == ["config.json"]
