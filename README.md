# number_audit

**Catch made-up numbers in LLM-written financial text.**

LLMs write fluent financial prose and quietly get the numbers wrong: "$402M revenue" when the
filing says $420M, or a 12.5x multiple described as a "12.5% margin". `number_audit` checks that
every dollar amount, percentage, multiple and count in a document matches a known figure,
**in the same unit, at the precision it was written**.

```
$ python number_audit.py examples/memo_hallucinated.md examples/figures.json
Unverified dollar amount `$402.00M` in: "...ictional) ## 1. Summary ACME generated $402.00M of revenue and $84.00M of EBITDA in FY2..."
Unverified percentage `12.50%` in: "...enue and $84.00M of EBITDA in FY2025, a 12.50% margin. ## 2. Valuation - Enterprise v..."
Unverified percentage `11.2%` in: "...er median: 14.00x, so ACME trades at an 11.2% discount. - The company operates 6 plan..."
Unverified number `6` in: "...11.2% discount. - The company operates 6 plants across the Midwest...."
4 unverified number(s).
```

Pure Python, a single file, no dependencies. Python 3.11+.

## Use it

```python
from number_audit import Figure, audit

facts = [
    Figure("revenue", 420.0, "money_mm"),    # money in $ millions
    Figure("ebitda_margin", 20.0, "pct"),    # percentages as written: 20.0 = 20%
    Figure("ev_to_ebitda", 12.5, "multiple"),
]

for finding in audit(llm_output, facts):
    print(finding)        # or feed findings back to the model as revision instructions
```

Or from the command line, with figures in JSON (`{"revenue": {"value": 420, "unit": "money_mm"}}`):

```
python number_audit.py memo.md figures.json   # exit code 1 if anything is unverified
```

## What it checks

| Written | Truth | Result | Why |
|---|---|---|---|
| `$1.05B` | 1,050 ($M) | ✅ | Billions are normalised to millions; tolerance follows written precision (±$5M) |
| `$1050M`, `$1,050.00M` | 1,050 ($M) | ✅ | Thousands separators optional |
| `a 10.71% discount` | −10.71% | ✅ | Sign can be expressed in words |
| `$20.00M` | 20% margin | ❌ | Same number, wrong unit |
| `12.50%` | 12.5x multiple | ❌ | Same number, wrong unit |
| `20.04%` | 20.00% | ❌ | Outside the precision written (±0.005) |
| `3 plants` | none | ❌ | Bare counts must match some figure |
| `FY2025`, `Q2`, `10-K`, `## 2.` | | ignored | Years, labels and list numbering aren't claims |
| URLs, Markdown link targets | | ignored | Their digits aren't claims |

## Limits

It proves each number **exists in your data and is in the right unit**. It doesn't prove the
number is attached to the right metric: "EBITDA of $420M" passes if $420M is the revenue. In
practice, pair it with having the model write placeholders (`{{revenue}}`) that code fills in,
and use the auditor to catch anything the model typed itself.

## Run the tests

```
pip install pytest
pytest
```

## Background

This is the audit step from the [M&A Due-Diligence Briefing Engine](https://rickster777.gumroad.com/l/juzevi),
which writes briefing memos from SEC filings with the model using placeholders and every
remaining number checked by this code. There's also a companion
[DCF & LBO Model Generator](https://rickster777.gumroad.com/l/sypqgi) that builds fully linked
Excel models. Both are paid tools; this auditor is free and MIT-licensed.

Issues and pull requests are welcome, especially examples where it gets something wrong.
