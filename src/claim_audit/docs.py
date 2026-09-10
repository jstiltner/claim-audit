"""Reading the prose side of a repository.

Everything the doc-facing checks share: which files count as documentation, where the code
fences are, and how to pull a markdown table apart. Code fences matter a lot here — a
numeral inside a fenced example is illustrative, and a check that cannot tell prose from a
code sample will spend its whole life reporting sample data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DOCS = ("README.md", "*.md", "docs/**/*.md")
DEFAULT_DOC_EXCLUDE = (
    "**/node_modules/**",
    "**/.venv/**",
    "**/CHANGELOG.md",
    "**/LICENSE*",
)

_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Line:
    number: int
    text: str
    in_fence: bool


def read_lines(path: Path) -> list[Line]:
    """Lines of a markdown file, each marked as inside or outside a code fence."""
    try:
        raw = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []

    out: list[Line] = []
    fence: str | None = None
    for number, text in enumerate(raw, start=1):
        match = _FENCE.match(text)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
                out.append(Line(number, text, True))
                continue
            if text.strip().startswith(fence):
                fence = None
                out.append(Line(number, text, True))
                continue
        out.append(Line(number, text, fence is not None))
    return out


def collect_docs(repo: Path, patterns: list[str], exclude: list[str]) -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in patterns:
        for match in sorted(repo.glob(pattern)):
            if not match.is_file():
                continue
            rel = match.relative_to(repo)
            if any(match.match(x) or rel.match(x) for x in exclude):
                continue
            seen[match] = None
    return list(seen)


# --- markdown tables ----------------------------------------------------------------

_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


@dataclass(frozen=True)
class Row:
    cells: tuple[str, ...]
    lineno: int


@dataclass(frozen=True)
class Table:
    header: tuple[str, ...]
    rows: tuple[Row, ...]
    header_lineno: int


def _split(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return tuple(c.strip() for c in stripped.split("|"))


def parse_tables(lines: list[Line]) -> list[Table]:
    """Pipe tables outside code fences.

    A table needs a header, a separator row of dashes, and at least one body row. Anything
    that doesn't have all three is not treated as a table at all — GFM is more forgiving
    than this, and being more forgiving here would mean parsing ASCII art as data.
    """
    tables: list[Table] = []
    i = 0
    while i < len(lines) - 1:
        head, sep = lines[i], lines[i + 1]
        if head.in_fence or "|" not in head.text or not _SEPARATOR.match(sep.text):
            i += 1
            continue

        header = _split(head.text)
        if len(header) < 2 or len(_split(sep.text)) != len(header):
            i += 1
            continue

        rows: list[Row] = []
        j = i + 2
        while j < len(lines) and "|" in lines[j].text and not lines[j].in_fence:
            cells = _split(lines[j].text)
            if len(cells) == len(header):
                rows.append(Row(cells, lines[j].number))
            j += 1

        if rows:
            tables.append(Table(header, tuple(rows), head.number))
        i = max(j, i + 1)
    return tables
