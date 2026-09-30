"""German telephone numbers: which ones are plausible, and how they are written.

The rules follow the Bundesnetzagentur's numbering plans:

- A number is dialled with its area code: it starts with 0, or with +49 /
  0049 in place of that 0.
- Mobile numbers start with 015, 0160, 0162, 0163 or 017 and have 10 or 11
  digits after the 0 (11 or 12 as typed, e.g. 0171 1234567).
- Landline numbers: one of the 5200 area codes (two to five digits, see
  german_area_codes.py), then the subscriber's number. New numbers have 11
  digits after the 0 (10 in Berlin, Hamburg, Frankfurt and München), older
  ones are shorter, and an extension may bring them up to 13.

The spelling follows DIN 5008: the area code, one space, then the number
in one piece - "0171 1234567", "089 1234567". An extension keeps its
hyphen: "089 12345-67". Numbers entered as +49 ... are written the same
national way, so that every number in the client list looks alike.

Numbers of other countries (+43 ..., 0041 ...) are only checked for their
length and keep the grouping they were typed with.
"""

from __future__ import annotations

import re

from klientenverwaltung.services.german_area_codes import AREA_CODES

# Digits with the usual separators between them, optionally opened by "+"
# (country code) or "(" - "(089) 123456". Anything else is a slip of the
# keyboard: letters, a "+" in the middle, a separator at the end.
_SHAPE_RE = re.compile(r"[+(]?[0-9](?:[0-9 ()/.-]*[0-9])?")
_SEPARATORS_RE = re.compile(r"[ ()/.]")

# What a mobile number starts with after the leading 0, and how many digits
# it then has in all (again without that 0). The numbering plan gives 015
# exactly 11, but one length for every prefix is deliberate: a real number
# that is refused keeps its client from being saved at all, which is worse
# than a missing digit that goes unnoticed.
_MOBILE_PREFIXES = ("15", "160", "162", "163", "17")
_MOBILE_DIGITS = (10, 11)
_MOBILE_PREFIX_LENGTH = 3  # "171" of 0171 1234567

# Numbers without an area code that someone may still be reached under:
# national subscriber numbers (032, used for internet telephony), personal
# numbers (0700) and free-phone numbers (0800).
_OTHER_PREFIXES = ("32", "700", "800")

_MIN_SUBSCRIBER_DIGITS = 3
_MAX_NATIONAL_DIGITS = 13
_MIN_NATIONAL_DIGITS_WITHOUT_AREA_CODE = 8
# E.164: at most 15 digits with the country code.
_FOREIGN_DIGITS = range(7, 16)

_EXAMPLES = "zum Beispiel 0171 1234567 oder 089 1234567"
_SHAPE_MESSAGE = (
    f"Bitte die Nummer mit Vorwahl eingeben, {_EXAMPLES}. Außer Ziffern sind "
    "nur Leerzeichen und die Zeichen + / - . ( ) erlaubt."
)


class PhoneNumberError(ValueError):
    """Not a plausible telephone number - the (German) message says why."""


def normalize_phone(value: str) -> str:
    """value in the standard spelling (see the module docstring), e.g.
    "+49 (0) 171 1234567" -> "0171 1234567", "089/123456-78" ->
    "089 123456-78". Raises PhoneNumberError for anything that cannot be a
    telephone number."""
    text = " ".join(value.split())
    if not _SHAPE_RE.fullmatch(text):
        raise PhoneNumberError(_SHAPE_MESSAGE)
    if not text.startswith(("+", "00")):
        return _format_national(_SEPARATORS_RE.sub("", text))
    # "+49 (0) 171 ...": the bracketed 0 is not dialled after a country code.
    text = text.replace("(0)", " ", 1)
    compact = _SEPARATORS_RE.sub("", text)
    compact = compact[1:] if compact.startswith("+") else compact[2:]
    if not compact.startswith("49"):
        return _format_foreign(text)
    national = compact[2:].lstrip("-")
    # "+49 0171 ..." is a common slip - the 0 belongs there only once.
    return _format_national(national if national.startswith("0") else f"0{national}")


def format_phone(value: str | None) -> str | None:
    """value as it is shown: in the standard spelling if it is a plausible
    number, unchanged otherwise (an entry from before these rules existed -
    it is shown as it is and corrected the next time the client is saved)."""
    if not value:
        return value
    try:
        return normalize_phone(value)
    except PhoneNumberError:
        return value


def _format_national(national: str) -> str:
    """national: digits, possibly with hyphens between them, as dialled
    within Germany ("0171-1234567", "089123456-78")."""
    digits = national.replace("-", "")
    if not digits.startswith("0") or digits.startswith("00"):
        raise PhoneNumberError(
            f"Bitte die Nummer mit Vorwahl eingeben, {_EXAMPLES}. Die Vorwahl "
            "beginnt mit 0."
        )
    number = digits[1:]
    if number.startswith("1"):
        return _format_mobile(number)
    if number.startswith(_OTHER_PREFIXES):
        prefix = next(p for p in _OTHER_PREFIXES if number.startswith(p))
        if not (
            _MIN_NATIONAL_DIGITS_WITHOUT_AREA_CODE
            <= len(number)
            <= _MAX_NATIONAL_DIGITS
        ):
            raise PhoneNumberError(
                f"Die Nummer hat nicht die richtige Länge für die Vorwahl 0{prefix}."
            )
        return f"0{prefix} {number[len(prefix) :]}"
    return _format_landline(national, number)


def _format_mobile(number: str) -> str:
    prefix = f"0{number[:_MOBILE_PREFIX_LENGTH]}"
    if not number.startswith(_MOBILE_PREFIXES):
        raise PhoneNumberError(
            f"{prefix} ist keine Mobilfunkvorwahl. Mobilnummern beginnen mit "
            "015, 0160, 0162, 0163 oder 017."
        )
    if len(number) not in _MOBILE_DIGITS:
        # Counted with the leading 0, the way the number is typed.
        expected = " oder ".join(str(length + 1) for length in _MOBILE_DIGITS)
        raise PhoneNumberError(
            f"Eine Mobilnummer hat mit Vorwahl {expected} Ziffern, "
            f"eingegeben sind {len(number) + 1}."
        )
    return f"{prefix} {number[_MOBILE_PREFIX_LENGTH:]}"


def _format_landline(national: str, number: str) -> str:
    # Longest first: 2129 (Haan) before 212 (Solingen), the one pair where
    # an area code is the beginning of another.
    area_code = next(
        (number[:length] for length in (5, 4, 3, 2) if number[:length] in AREA_CODES),
        None,
    )
    if area_code is None:
        raise PhoneNumberError(
            "Die Vorwahl ist nicht bekannt - bitte die ersten Ziffern prüfen, "
            f"{_EXAMPLES}."
        )
    subscriber = number[len(area_code) :]
    if len(subscriber) < _MIN_SUBSCRIBER_DIGITS:
        raise PhoneNumberError(
            f"Die Nummer ist zu kurz: Nach der Vorwahl 0{area_code} fehlen Ziffern."
        )
    if len(number) > _MAX_NATIONAL_DIGITS:
        raise PhoneNumberError(
            f"Die Nummer ist zu lang: Mit Vorwahl sind es höchstens "
            f"{_MAX_NATIONAL_DIGITS + 1} Ziffern, eingegeben sind {len(number) + 1}."
        )
    extension_at = _extension_hyphen(national, area_digits=1 + len(area_code))
    if extension_at is not None:
        split = extension_at - 1 - len(area_code)
        subscriber = f"{subscriber[:split]}-{subscriber[split:]}"
    return f"0{area_code} {subscriber}"


def _extension_hyphen(national: str, *, area_digits: int) -> int | None:
    """How many digits of national stand before the hyphen that sets off an
    extension ("089 12345-67") - None if there is no such hyphen.

    A hyphen right after the area code ("089-1234567") only separates the
    two, and several hyphens ("089 12-34-56") only group the digits: both
    are dropped.
    """
    positions = []
    digits_before = 0
    for character in national:
        if character == "-":
            positions.append(digits_before)
        else:
            digits_before += 1
    inside = [position for position in positions if position > area_digits]
    return inside[0] if len(inside) == 1 else None


def _format_foreign(text: str) -> str:
    """text starts with "+" or "00" and another country's code. The digits
    keep their grouping; only the separators are unified to spaces."""
    digits = re.sub(r"[^0-9]", "", text)
    if text.startswith("00"):
        digits = digits[2:]
        text = f"+{text[2:]}"
    if digits.startswith("0") or len(digits) not in _FOREIGN_DIGITS:
        raise PhoneNumberError(_SHAPE_MESSAGE)
    return "+" + " ".join(re.sub(r"[^0-9]+", " ", text).split())
