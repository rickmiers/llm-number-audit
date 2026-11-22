"""number_audit: catch made-up numbers in LLM-written financial text.

Every dollar amount, percentage, multiple and bare count in a document must match a
known ground-truth figure *of the same unit*, at the precision it was written.

    >>> facts = [Figure("revenue", 420.0, "money_mm"), Figure("margin", 20.0, "pct")]
    >>> audit("Revenue was $420.0M at a 20% margin.", facts)
    []
    >>> [f.token for f in audit("Revenue was $20.00M.", facts)]
    ['$20.00M']

Pure Python, no dependencies. MIT licensed.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Iterable, Literal

__version__ = "0.1.0"
__all__ = ["Figure", "NumberToken", "Finding", "tokenize_numbers", "audit", "load_figures"]

Unit = Literal["money_mm", "pct", "multiple", "count"]
TokenKind = Literal["money_mm", "pct", "multiple", "count", "structural"]

UNIT_NAMES = {"money_mm": "dollar amount", "pct": "percentage", "multiple": "multiple", "count": "number"}


@dataclass(frozen=True)
class Figure:
    """A ground-truth value. Money is in millions ($M); percentages as written (20.0 = 20%)."""

    name: str
    value: float
    unit: Unit


@dataclass(frozen=True)
class NumberToken:
    raw: str
    value: float          # normalised: money in $M, so "$1.05B" -> 1050.0
    kind: TokenKind
    decimals: int
    scale: float          # 1000 for billions, else 1
    start: int
    end: int


@dataclass(frozen=True)
class Finding:
    token: str
    unit: str
    context: str
    start: int

    def __str__(self) -> str:
        return f'Unverified {UNIT_NAMES.get(self.unit, self.unit)} `{self.token}` in: "...{self.context}..."'


# A number not glued to a preceding word or number (so "FY2025", "Q2", "PEER1" and the
# middle of "1,050.00" are never tokenised), with an optional sign, "$" and unit.
_NUMBER = re.compile(
    r"(?<![\w.,$])"
    r"(?P<sign1>[-+−])?(?P<dollar>\$)?(?P<sign2>[-+−])?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<unit>%|x|X|MM|mm|M|bn|B|million|billion)(?![A-Za-z0-9]))?"
    r"(?!\w|[.,]\d|-[A-Za-z])"
)
_LIST_MARKER_PREFIX = re.compile(r"^\s*(?:#+\s*)?(?:[-*]\s*)?$")


def tokenize_numbers(text: str) -> list[NumberToken]:
    """Find every number in ``text`` and classify its unit.

    Years (1900-2100) and list/section numbering ("1." at the start of a line) are
    marked ``structural`` and are not claims.
    """
    tokens: list[NumberToken] = []
    for m in _NUMBER.finditer(text):
        num = m.group("num")
        value = float(num.replace(",", ""))
        if (m.group("sign1") or m.group("sign2") or "") in ("-", "−"):
            value = -value
        decimals = len(num.split(".")[1]) if "." in num else 0
        unit = m.group("unit") or ""
        scale = 1.0

        if unit == "%":
            kind: TokenKind = "pct"
        elif unit in ("x", "X"):
            kind = "multiple"
        elif unit in ("B", "bn", "billion"):
            kind, scale = "money_mm", 1000.0
        elif unit in ("M", "MM", "mm", "million") or m.group("dollar"):
            kind = "money_mm"
        else:
            kind = "count"
            line_start = text.rfind("\n", 0, m.start()) + 1
            prefix = text[line_start:m.start()]
            is_year = decimals == 0 and 1900 <= abs(value) <= 2100
            is_list_marker = (decimals == 0 and text[m.end():m.end() + 1] == "."
                              and _LIST_MARKER_PREFIX.match(prefix) is not None)
            if is_year or is_list_marker:
                kind = "structural"

        tokens.append(NumberToken(m.group(0), value * scale, kind, decimals, scale, m.start(), m.end()))
    return tokens


def _matches(tok: NumberToken, candidates: Iterable[Figure]) -> bool:
    # Half a unit in the last written decimal place: "20.00%" must be within 0.005,
    # "$1.05B" within $5M, "14x" within 0.5x. Sign may be expressed in words ("a 10% discount").
    tol = 0.5 * 10 ** (-tok.decimals) * tok.scale + 1e-9
    return any(abs(tok.value - f.value) <= tol or abs(abs(tok.value) - abs(f.value)) <= tol
               for f in candidates)


def audit(text: str, figures: Iterable[Figure], *, context_chars: int = 40) -> list[Finding]:
    """Return one Finding per number in ``text`` that no same-unit figure backs up.

    Bare numbers ("3 plants") must match some figure of any unit. Markdown link targets
    and bare URLs are ignored, since their digits aren't claims.
    """
    figures = list(figures)
    cleaned = re.sub(r"\]\([^)]*\)", "]()", text)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    by_unit: dict[str, list[Figure]] = {}
    for f in figures:
        by_unit.setdefault(f.unit, []).append(f)

    findings: list[Finding] = []
    for tok in tokenize_numbers(cleaned):
        if tok.kind == "structural":
            continue
        candidates = figures if tok.kind == "count" else by_unit.get(tok.kind, [])
        if not _matches(tok, candidates):
            lo, hi = max(0, tok.start - context_chars), min(len(cleaned), tok.end + context_chars)
            findings.append(Finding(tok.raw.strip(), tok.kind, " ".join(cleaned[lo:hi].split()), tok.start))
    return findings


def load_figures(data: dict) -> list[Figure]:
    """Load figures from ``{"name": {"value": 420.0, "unit": "money_mm"}, ...}``."""
    out = []
    for name, spec in data.items():
        unit = spec["unit"]
        if unit not in UNIT_NAMES:
            raise ValueError(f"{name}: unit must be one of {', '.join(UNIT_NAMES)}, got {unit!r}")
        out.append(Figure(name, float(spec["value"]), unit))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python number_audit.py MEMO.md FIGURES.json", file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        text = fh.read()
    with open(argv[1], encoding="utf-8") as fh:
        figures = load_figures(json.load(fh))
    findings = audit(text, figures)
    for f in findings:
        print(f)
    print(f"{len(findings)} unverified number(s)." if findings else "All numbers verified.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
