import pytest

from klientenverwaltung.services.phone import (
    PhoneNumberError,
    format_phone,
    normalize_phone,
)


@pytest.mark.parametrize(
    "entered,expected",
    [
        # Mobile: 11 or 12 digits as typed, whatever the prefix.
        ("0171 1234567", "0171 1234567"),
        ("0151 1234567", "0151 1234567"),
        ("01711234567", "0171 1234567"),
        ("0171/123 45 67", "0171 1234567"),
        ("0171-123-4567", "0171 1234567"),
        ("0176 12345678", "0176 12345678"),
        ("0151 12345678", "0151 12345678"),
        # +49 / 0049 in place of the 0 - written the national way.
        ("+49 171 1234567", "0171 1234567"),
        ("+49 (0) 171 1234567", "0171 1234567"),
        ("+49 0171 1234567", "0171 1234567"),
        ("0049 171 1234567", "0171 1234567"),
        ("+49 89 1234567", "089 1234567"),
        # Landline: the area code is found in the Bundesnetzagentur's list,
        # however the number was grouped when typed.
        ("0301234567", "030 1234567"),
        ("(089) 1234567", "089 1234567"),
        ("089/1234567", "089 1234567"),
        ("089-1234567", "089 1234567"),
        ("0711 12 34 56 7", "0711 1234567"),
        ("07151123456", "07151 123456"),
        ("0 71 51 / 12 34 56", "07151 123456"),
        ("033203 12345", "033203 12345"),
        ("04862 123", "04862 123"),
        # 2129 (Haan) is the one area code that starts like another (212).
        ("0212 123456", "0212 123456"),
        ("02129 12345", "02129 12345"),
        # An extension keeps its hyphen.
        ("089/123456-78", "089 123456-78"),
        ("+49 89 123456-78", "089 123456-78"),
        # Numbers without an area code.
        ("0800 1234567", "0800 1234567"),
        ("032 123456789", "032 123456789"),
        # Other countries: only the separators are unified.
        ("+43 660 1234567", "+43 660 1234567"),
        ("0041 (0) 79/123 45 67", "+41 79 123 45 67"),
    ],
)
def test_numbers_are_written_in_the_standard_spelling(
    entered: str, expected: str
) -> None:
    assert normalize_phone(entered) == expected
    # What was normalized once stays as it is.
    assert normalize_phone(expected) == expected


@pytest.mark.parametrize(
    "entered,reason",
    [
        ("0171 1234567 abends", "erlaubt"),
        ("0171+1234567", "erlaubt"),
        ("089 1234567-", "erlaubt"),
        ("1234567", "mit Vorwahl"),
        ("0171 123456", "11 oder 12 Ziffern"),
        ("0171 123456789", "11 oder 12 Ziffern"),
        ("0151 123456", "11 oder 12 Ziffern"),
        ("0123 456789", "keine Mobilfunkvorwahl"),
        ("0999 123456", "Vorwahl ist nicht bekannt"),
        ("089 12", "zu kurz"),
        ("089 1234567890123", "zu lang"),
        ("+43 12", "mit Vorwahl"),
    ],
)
def test_implausible_numbers_are_rejected_with_the_reason(
    entered: str, reason: str
) -> None:
    with pytest.raises(PhoneNumberError, match=reason):
        normalize_phone(entered)


def test_format_phone_leaves_an_implausible_stored_number_unchanged() -> None:
    assert format_phone("0171/1234567") == "0171 1234567"
    assert format_phone("12345") == "12345"
    assert format_phone(None) is None
