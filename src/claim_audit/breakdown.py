"""breakdown-sums: do the parts add up to the stated whole?

Mode 3. A table gives a breakdown, and a row labelled Total gives a figure that is not the
sum of the rows above it. This is arithmetic, so it is Tier A — but only if the check
refuses every case where "total" might mean something other than addition.

The refusals are the whole design. It fires only on a table with exactly one total-labelled
row, at least two other rows, a column of plain non-negative integers, and an exact
mismatch. Percentages, decimals, ranges, blanks and second total rows all disqualify the
column, because in every one of those cases a total that differs from the sum can be
correct.

Narrower than SPEC §4, which also allowed a caption to imply a total. Inferring a total
from prose is not arithmetic, so it is out.
"""

from __future__ import annotations

import re
from pathlib import Path

from claim_audit.docs import Table, collect_docs, parse_tables, read_lines
from claim_audit.finding import CheckResult, Finding

RULE = "breakdown-sums"

_TOTAL = re.compile(
    r"^\**\s*(sub-?totals?|totals?|sum|overall|all|combined)\b[\s:]*\**$", re.I
)
_INT = re.compile(r"^\**(\d{1,3}(?:,\d{3})+|\d+)\**$")


def _as_int(cell: str) -> int | None:
    match = _INT.match(cell.strip())
    return int(match.group(1).replace(",", "")) if match else None


def _label(row) -> str:
    return row.cells[0] if row.cells else ""


def check_table(table: Table, path: str) -> list[Finding]:
    total_rows = [r for r in table.rows if _TOTAL.match(_label(r))]
    if len(total_rows) != 1:
        # Zero: nothing claims to be a total. Two or more: nested subtotals, where summing
        # every non-total row is the wrong arithmetic.
        return []

    total_row = total_rows[0]
    parts = [r for r in table.rows if r is not total_row]
    if len(parts) < 2:
        return []

    findings: list[Finding] = []
    for col in range(1, len(table.header)):
        header = table.header[col]
        if "%" in header or "%" in total_row.cells[col]:
            continue

        stated = _as_int(total_row.cells[col])
        if stated is None:
            continue

        values = [_as_int(r.cells[col]) for r in parts]
        if any(v is None for v in values):
            # A blank, a decimal, a range, an n/a — anything that isn't a plain count.
            continue

        actual = sum(values)  # type: ignore[arg-type]
        if actual == stated:
            continue

        column = header or f"column {col}"
        findings.append(
            Finding(
                rule=RULE,
                path=path,
                line=total_row.lineno,
                evidence=(
                    f'Table at line {table.header_lineno}, column "{column}".',
                    f"Rows above sum to {actual}: "
                    + " + ".join(str(v) for v in values),  # type: ignore[arg-type]
                    f'Row "{_label(total_row).strip("* ")}" states {stated}.',
                ),
                question=(
                    "Is a row missing from this breakdown, or is the total from a "
                    "different population?"
                ),
            )
        )
    return findings


def run(repo: Path, docs: list[str] | None = None, exclude: list[str] | None = None) -> CheckResult:
    from claim_audit.docs import DEFAULT_DOC_EXCLUDE, DEFAULT_DOCS

    paths = collect_docs(repo, list(docs or DEFAULT_DOCS), list(exclude or DEFAULT_DOC_EXCLUDE))
    result = CheckResult(rule=RULE, examined=len(paths))
    for path in paths:
        rel = path.relative_to(repo).as_posix()
        for table in parse_tables(read_lines(path)):
            result.findings.extend(check_table(table, rel))
    return result
