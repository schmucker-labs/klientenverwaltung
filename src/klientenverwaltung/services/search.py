"""Search-box matching as a person expects it, independent of the database.

Done in Python rather than as SQL `ILIKE`: SQLite's lower() only folds
ASCII, so "über" never found "Überlingen", and a single LIKE per column
never found a full name like "Anna Muster". At the size of a one-person
practice (hundreds of clients, not millions) filtering the loaded rows is
instant, and it keeps repositories free of database-specific behavior.
"""

import unicodedata


def fold(text: str) -> str:
    """Case- and accent-insensitive form: "Özdemir" -> "ozdemir",
    "Straße" -> "strasse"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def search_terms(search: str | None) -> list[str]:
    """The folded, whitespace-separated terms of a search text ([] = no filter)."""
    return fold(search).split() if search else []


def matches(terms: list[str], *values: str | None) -> bool:
    """True if every term occurs in at least one of values.

    "Anna Muster" therefore finds first name "Anna" + last name "Muster",
    in either order, while "Anna Özdemir" finds neither of two different
    clients named Anna and Özdemir.
    """
    folded = [fold(value) for value in values if value]
    return all(any(term in value for value in folded) for term in terms)
