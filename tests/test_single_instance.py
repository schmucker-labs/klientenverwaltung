from pathlib import Path

from klientenverwaltung import main


def test_a_second_instance_cannot_take_the_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "klientenverwaltung.lock"
    first = main._acquire_single_instance_lock(lock_path)
    assert first is not None

    assert main._acquire_single_instance_lock(lock_path) is None

    first.unlock()
    again = main._acquire_single_instance_lock(lock_path)
    assert again is not None
    again.unlock()
