"""numeral-has-source: is a specific figure in the prose traceable to an artifact?

Mode 7. Narrowed per SPEC amendment A1 — the original rule ("every numeral has a
counterpart") could not hold Tier A's standard, because prose rounds numbers and rounding
would have made every reported figure an orphan.

What survives is narrow and, I think, defensible:

* Only **specific** figures are considered — a decimal point, or three or more significant
  digits. `18`, `53%` and `n=7` are not specific enough for their absence to mean anything,
  so they are neither hits nor orphans. They are not looked at.
* Matching is **rounding-tolerant**, and tolerant of the percent/fraction switch. Prose
  saying `53.4%` is satisfied by an artifact holding `0.534`, because those are the same
  number written for different readers.
* Years, versions, dates, issue numbers and section references are excluded by shape.

The source universe is every artifact and source file in the repository *except* markdown,
which is excluded so that prose cannot be its own evidence. Everything else is included
precisely because a wider universe can only suppress flags.
"""

from __future__ import annotations

import re
from pathlib import Path

from claim_audit.docs import (
    DEFAULT_DOC_EXCLUDE,
    DEFAULT_DOCS,
    collect_docs,
    read_lines,
)
from claim_audit.finding import CheckResult, Finding

RULE = "numeral-has-source"

SOURCE_GLOBS = (
    "**/*.json",
    "**/*.jsonl",
    "**/*.csv",
    "**/*.tsv",
    "**/*.txt",
    "**/*.yaml",
    "**/*.yml",
    "**/*.toml",
    "**/*.py",
    "**/*.js",
    "**/*.ts",
    "**/*.ipynb",
)
SOURCE_SKIP = ("node_modules", ".venv", "venv", ".git", "__pycache__", "site-packages", "dist")

MAX_SOURCE_BYTES = 8_000_000
"""Stop reading a single file past this size. A model checkpoint dumped as JSON is not
evidence about anybody's claims, and reading it whole would only slow the run down."""

# The trailing lookahead rejects dotted versions like `1.2.3` without also rejecting a
# figure that ends a sentence — `reached 0.871.` is the common case and an earlier
# `(?![\d.])` silently dropped every one of them.
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?!\.?\d)")
_INLINE_CODE = re.compile(r"`[^`]*`")
_LINK_URL = re.compile(r"\]\([^)]*\)|https?://\S+")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Words that, immediately before a figure, mean it is an identifier rather than a result.
_LABEL_BEFORE = re.compile(
    r"(?:^|[\s(\[])(?:"
    r"v|ver|version|python|node|cuda|§|section|sec|fig|figure|table|tbl|"
    r"exp|experiment|phase|step|chapter|part|issue|pr|#|port|seed"
    r")[\s.:#]*$",
    re.I,
)


def _is_specific(whole: str, frac: str | None) -> bool:
    """A decimal point, and at least three significant digits.

    Integers are excluded entirely — see amendment A2. The absence of an integer from the
    artifacts is much weaker evidence than the absence of a decimal, because integers are
    usually counts of things nobody stores as data (hospitals, tests, list elements) and
    because they collide by coincidence far more often.
    """
    if not frac:
        return False
    plain = (whole.replace(",", "").lstrip("0") + frac).lstrip("0")
    return len(plain) >= 3


def _mask(text: str) -> str:
    """Blank out spans where a figure is not a claim: code spans, URLs, dates."""
    for pattern in (_INLINE_CODE, _LINK_URL, _DATE):
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return text


def _collect_source_values(repo: Path) -> list[float]:
    values: list[float] = []
    seen: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        for path in repo.glob(pattern):
            if path in seen or not path.is_file():
                continue
            if any(part in SOURCE_SKIP for part in path.parts):
                continue
            seen.add(path)
            try:
                if path.stat().st_size > MAX_SOURCE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in _NUMBER.finditer(text):
                whole, frac = match.group(1).replace(",", ""), match.group(2)
                try:
                    values.append(float(f"{whole}.{frac}" if frac else whole))
                except ValueError:
                    continue
    return values


def _rounded_set(values: list[float], decimals: int) -> set[float]:
    """Every source value as the prose might have written it, at this precision.

    Includes the value scaled by 100 and by 1/100 so that a fraction in an artifact
    satisfies a percentage in the prose, and the other way round.
    """
    out: set[float] = set()
    for v in values:
        out.add(round(v, decimals))
        out.add(round(v * 100, decimals))
        out.add(round(v / 100, decimals))
    return out


def run(repo: Path, docs: list[str] | None = None, exclude: list[str] | None = None) -> CheckResult:
    repo = repo.resolve()
    paths = collect_docs(repo, list(docs or DEFAULT_DOCS), list(exclude or DEFAULT_DOC_EXCLUDE))
    result = CheckResult(rule=RULE, examined=len(paths))

    candidates: list[tuple[str, int, str, float, int]] = []
    for doc in paths:
        rel = doc.relative_to(repo).as_posix()
        for line in read_lines(doc):
            if line.in_fence:
                continue
            masked = _mask(line.text)
            for match in _NUMBER.finditer(masked):
                whole, frac = match.group(1), match.group(2)
                if not _is_specific(whole, frac):
                    continue
                if _LABEL_BEFORE.search(masked[: match.start()][-24:]):
                    continue
                plain = whole.replace(",", "")
                try:
                    value = float(f"{plain}.{frac}" if frac else plain)
                except ValueError:
                    continue
                candidates.append((rel, line.number, match.group(0), value, len(frac or "")))

    if not candidates:
        result.note = "no figures specific enough to trace"
        return result

    source_values = _collect_source_values(repo)
    if not source_values:
        result.note = "no artifacts or source files to trace figures to; check skipped"
        return result

    by_precision: dict[int, set[float]] = {}
    orphans: dict[str, list[tuple[str, int]]] = {}
    for rel, lineno, literal, value, decimals in candidates:
        if decimals not in by_precision:
            by_precision[decimals] = _rounded_set(source_values, decimals)
        if round(value, decimals) in by_precision[decimals]:
            continue
        orphans.setdefault(literal, []).append((rel, lineno))

    # One finding per distinct orphan value, not per occurrence. A single untraceable
    # results table repeated across a blog post and a slide deck is one gap; reporting it
    # twenty-seven times would let the loudest gap dominate any precision figure computed
    # later, which is the measurement error this project is about.
    for literal, sites in orphans.items():
        first_path, first_line = sites[0]
        evidence = [
            f"`{literal}` appears in prose here.",
            "No artifact or source file in this repository holds that value, "
            "at this precision or as a percentage of it.",
        ]
        if len(sites) > 1:
            others = ", ".join(f"{p}:{n}" for p, n in sites[1:6])
            more = f", and {len(sites) - 6} more" if len(sites) > 6 else ""
            evidence.append(f"Also at {others}{more}.")
        result.findings.append(
            Finding(
                rule=RULE,
                path=first_path,
                line=first_line,
                evidence=tuple(evidence),
                question="Where was this figure computed, and is that code in this repository?",
            )
        )
    return result
