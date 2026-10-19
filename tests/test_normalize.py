import pytest

from app.normalize import is_indonesian, parse_currency, parse_date


@pytest.mark.parametrize("raw,day_first,expected", [
    ("09/10/2026", True, "2026-10-09"),        # Indonesian: day first
    ("09/10/2026", False, "2026-09-10"),       # US: month first
    ("21/09/2026", False, "2026-09-21"),       # unambiguous beats the hint
    ("09/21/2026", True, "2026-09-21"),
    ("3 September 2026", True, "2026-09-03"),
    ("3 Oktober 2026", True, "2026-10-03"),
    ("Sept 3, 2026", False, "2026-09-03"),
    ("2026-08-31", False, "2026-08-31"),
    ("31/02/2026", True, None),                # not a real date
    ("", True, None),
])
def test_parse_date(raw, day_first, expected):
    assert parse_date(raw, day_first) == expected


@pytest.mark.parametrize("raw,expected", [("Rp", "IDR"), ("$", "USD"), ("usd", "USD"), ("€", "EUR"), ("SGD", "SGD")])
def test_parse_currency(raw, expected):
    assert parse_currency(raw) == expected


def test_language_detection():
    assert is_indonesian("FAKTUR\nTanggal 3 September 2026\nKepada PT X")
    assert not is_indonesian("INVOICE\nDate 09/10/2026\nBill To Example Ltd")
