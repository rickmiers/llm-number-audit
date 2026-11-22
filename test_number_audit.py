import json
from pathlib import Path

import pytest

from number_audit import Figure, audit, load_figures, main, tokenize_numbers

FACTS = [
    Figure("margin", 20.0, "pct"),
    Figure("ev", 1050.0, "money_mm"),
    Figure("ev_ebitda", 12.5, "multiple"),
    Figure("premium", -10.71, "pct"),
]


@pytest.mark.parametrize("text", [
    "FY2025", "Q2 2025", "PEER1", "per its 10-K filing", "## 2. Financials", "1. Validate", "in 2025.",
])
def test_structural_numbers_are_not_claims(text):
    assert audit(text, FACTS) == []


@pytest.mark.parametrize("text", [
    "EV of $1,050.00M",
    "EV of $1050M",
    "EV of $1.05B",
    "margin of 20.00%",
    "12.50x EV/EBITDA",
    "a -10.71% discount",
    "a 10.71% discount",
    "In 2025, EV was $1.05B, margin 20.00%, multiple 12.50x.",
])
def test_correct_figures_pass(text):
    assert audit(text, FACTS) == []


@pytest.mark.parametrize("text,token", [
    ("Revenue was $20.00M.", "$20.00M"),         # matches the margin's number, wrong unit
    ("EBITDA margin of 12.50%.", "12.50%"),      # matches the multiple's number, wrong unit
    ("margin of 20.04%", "20.04%"),              # drift beyond written precision
    ("ACME has 3 plants", "3"),                  # invented count
    ("EV of $1.10B, which is high", "$1.10B"),   # followed by a comma
    ("EV of $1,051.00M", "$1,051.00M"),
])
def test_wrong_figures_are_flagged(text, token):
    findings = audit(text, FACTS)
    assert [f.token for f in findings] == [token]


def test_urls_are_ignored():
    assert audit("See the [10-K](https://sec.gov/Archives/edgar/data/320193/0001.htm) and https://x.com/1234", FACTS) == []


def test_tokenizer_units():
    toks = [(t.value, t.kind) for t in tokenize_numbers("$1.5B, 12.5 x, 20%, $-5.00M, 7")]
    assert toks == [(1500.0, "money_mm"), (12.5, "multiple"), (20.0, "pct"), (-5.0, "money_mm"), (7.0, "count")]


def test_malformed_thousands_not_half_parsed():
    assert all(t.raw != "1" for t in tokenize_numbers("$1,0500M"))


def test_finding_message():
    (f,) = audit("Revenue was $20.00M.", FACTS)
    assert str(f).startswith("Unverified dollar amount `$20.00M`")


def test_load_figures_validates_units():
    assert load_figures({"r": {"value": 1, "unit": "pct"}}) == [Figure("r", 1.0, "pct")]
    with pytest.raises(ValueError, match="unit must be"):
        load_figures({"r": {"value": 1, "unit": "percent"}})


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_cli_on_examples(capsys):
    assert main([str(EXAMPLES / "memo_good.md"), str(EXAMPLES / "figures.json")]) == 0
    assert "All numbers verified." in capsys.readouterr().out
    assert main([str(EXAMPLES / "memo_hallucinated.md"), str(EXAMPLES / "figures.json")]) == 1
    out = capsys.readouterr().out
    assert "$402.00M" in out and "12.50%" in out and "4 unverified number(s)." in out


def test_example_figures_file_is_valid():
    load_figures(json.loads((EXAMPLES / "figures.json").read_text()))
