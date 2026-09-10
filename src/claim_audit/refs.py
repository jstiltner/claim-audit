"""ref-resolves: does a citation in the docs point at something that exists?

Modes 4 and 8. Local, offline and deterministic — the half of SPEC §4's `link-resolves`
that needs no network (see amendment A1). URL fetching lives in `online.py` and is not
Tier A.

Two things get checked, both chosen because they cannot be misread as illustrative:

1. **Markdown links with relative targets.** `[the runner](experiments/run.py)` is an
   unambiguous claim that the path exists. If it doesn't, the link is broken.
2. **`path:line` citations whose file exists.** If the file is 200 lines and the doc cites
   line 340, the citation moved. Only checked when the file resolves, so a renamed
   directory produces silence rather than a guess.

A bare path mentioned in prose is checked only when its parent directory exists in the
repo. Without that guard the check would report every `path/to/your/config.yml` in every
usage example as a broken reference.
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

RULE = "ref-resolves"

_LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s#][^)\s]*?)\s*(?:\"[^\"]*\")?\)")
_CITATION = re.compile(r"`([\w./-]+\.[A-Za-z0-9]{1,6}):(\d+)`|(?<![\w/])([\w./-]+\.py):(\d+)")

_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_PLACEHOLDER = re.compile(r"[<>*{}]|\bpath/to\b|\byour[-_/]|\bexample\b", re.I)

# `[auth](src/context/AuthContext.jsx:1-8)` — the target is a path plus a line or a range,
# not a filename ending in a colon. Reading it literally made the check report existing
# files as missing.
_TARGET_LINES = re.compile(r"^(.*?):(\d+)(?:-(\d+))?$")

# A link written inside a code span is syntax being shown, not a reference being made.
# Citations are exempt: `run.py:40` is a normal way to write one.
_INLINE_CODE = re.compile(r"`[^`]*`")


def _is_local_target(target: str) -> bool:
    if not target or target.startswith("#"):
        return False
    if _SCHEME.match(target) or target.startswith("//"):
        return False
    return not _PLACEHOLDER.search(target)


def _resolve(repo: Path, doc: Path, target: str) -> Path | None:
    """Try the target relative to the doc, then to the repo root.

    Both spellings appear in real docs and both are correct depending on how the file is
    rendered, so a reference resolving either way is treated as resolving.
    """
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    for base in (doc.parent, repo):
        candidate = (base / target).resolve()
        try:
            candidate.relative_to(repo.resolve())
        except ValueError:
            continue
        if candidate.exists():
            return candidate
    return None


def _line_count(path: Path) -> int | None:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return None


def run(repo: Path, docs: list[str] | None = None, exclude: list[str] | None = None) -> CheckResult:
    repo = repo.resolve()
    paths = collect_docs(repo, list(docs or DEFAULT_DOCS), list(exclude or DEFAULT_DOC_EXCLUDE))
    result = CheckResult(rule=RULE, examined=len(paths))

    for doc in paths:
        rel = doc.relative_to(repo).as_posix()
        for line in read_lines(doc):
            if line.in_fence:
                continue

            outside_code = _INLINE_CODE.sub(lambda m: " " * len(m.group(0)), line.text)
            for match in _LINK.finditer(outside_code):
                target = match.group(1)
                if not _is_local_target(target):
                    continue

                cited_line: int | None = None
                lines_match = _TARGET_LINES.match(target)
                if lines_match and lines_match.group(1):
                    target = lines_match.group(1)
                    cited_line = int(lines_match.group(3) or lines_match.group(2))

                resolved = _resolve(repo, doc, target)
                if resolved is None:
                    result.findings.append(
                        Finding(
                            rule=RULE,
                            path=rel,
                            line=line.number,
                            evidence=(
                                f"Link target `{target}` does not exist, "
                                "relative to this file or to the repository root.",
                            ),
                            question="Was this file moved, renamed, or never committed?",
                        )
                    )
                    continue

                if cited_line is not None and resolved.is_file():
                    count = _line_count(resolved)
                    if count is not None and cited_line > count:
                        result.findings.append(
                            Finding(
                                rule=RULE,
                                path=rel,
                                line=line.number,
                                evidence=(
                                    f"Links to `{target}:{cited_line}`.",
                                    f"{resolved.relative_to(repo).as_posix()} has {count} lines.",
                                ),
                                question=(
                                    "Has this file changed since the link was written, and "
                                    "does the claim still hold at the new location?"
                                ),
                            )
                        )

            for match in _CITATION.finditer(line.text):
                target = match.group(1) or match.group(3)
                lineno = int(match.group(2) or match.group(4))
                if not _is_local_target(target):
                    continue
                resolved = _resolve(repo, doc, target)
                if resolved is None or not resolved.is_file():
                    # Silence, not a guess: an unresolvable path here is more often a
                    # reference into another repository than a broken one.
                    continue
                count = _line_count(resolved)
                if count is not None and lineno > count:
                    result.findings.append(
                        Finding(
                            rule=RULE,
                            path=rel,
                            line=line.number,
                            evidence=(
                                f"Cites `{target}:{lineno}`.",
                                f"{resolved.relative_to(repo).as_posix()} has {count} lines.",
                            ),
                            question=(
                                "Has this file changed since the citation was written, and "
                                "does the claim still hold at the new location?"
                            ),
                        )
                    )
    return result
