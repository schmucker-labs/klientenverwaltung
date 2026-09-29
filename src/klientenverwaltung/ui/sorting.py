"""Sort keys for German text in tables.

A plain casefold()/code-point comparison puts "Özdemir" and "Ärmel" after
"Zimmer"; German collation sorts umlauts with their base letter, the way a
German reader looks for a name.
"""

from functools import cmp_to_key
from typing import Any

from PySide6.QtCore import QCollator, QLocale, Qt

_COLLATOR = QCollator(QLocale(QLocale.Language.German, QLocale.Country.Germany))
_COLLATOR.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
_COLLATION_KEY = cmp_to_key(_COLLATOR.compare)


def german_sort_key(text: str | None) -> Any:
    """A key that orders text the German way (None sorts like "")."""
    return _COLLATION_KEY(text or "")
