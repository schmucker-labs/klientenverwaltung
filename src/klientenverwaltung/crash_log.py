"""Technical crash details for the developer - without any content.

The log lives in %APPDATA% on the laptop, which must never hold client data
unencrypted (CLAUDE.md). Exception *messages* are exactly where such data
hides: SQL parameters, a client's name inside a validation message, a file
name, a pasted text fragment. So only exception types and code locations
are written - enough to find the failing line, never enough to reveal what
was being processed there.
"""

import traceback
from datetime import datetime
from pathlib import Path
from types import TracebackType

from klientenverwaltung import config

_OMITTED = "(message omitted - it may contain client data)"


def _exception_chain(exc_value: BaseException) -> list[BaseException]:
    """exc_value and every exception it was raised from or during,
    outermost first - the same chain traceback.format_exception() walks."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc_value
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return chain


def format_redacted(
    exc_value: BaseException, exc_tb: TracebackType | None = None
) -> str:
    """Like traceback.format_exception(), but every exception message is
    replaced by a placeholder. Source lines in the stack are program code,
    never data, so they stay."""
    parts: list[str] = []
    chain = _exception_chain(exc_value)
    for index, exc in enumerate(reversed(chain)):
        if index:
            parts.append("\nThe above exception led to the following one:\n\n")
        tb = exc_tb if exc is exc_value and exc_tb is not None else exc.__traceback__
        parts.append("Traceback (most recent call last):\n")
        parts.extend(traceback.format_list(traceback.extract_tb(tb)))
        exc_type = type(exc)
        parts.append(f"{exc_type.__module__}.{exc_type.__qualname__}: {_OMITTED}\n")
    return "".join(parts)


def write_crash_log(
    exc_value: BaseException, exc_tb: TracebackType | None = None
) -> Path:
    """Appends a redacted entry for exc_value to config.error_log_path()
    and returns that path. Never raises: failing to write the log must not
    turn one error into two."""
    log_path = config.error_log_path()
    details = format_redacted(exc_value, exc_tb)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n{details}\n")
    except OSError:
        pass
    return log_path
