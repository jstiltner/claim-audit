"""Command line entry point for the import-provenance check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from claim_audit import __version__
from claim_audit.provenance import (
    DEFAULT_EXCLUDE,
    DEFAULT_SCRIPTS,
    LOCAL_ONLY,
    NEITHER,
    PACKAGE,
    RepoReport,
    analyse_repo,
)

LABELS = {
    PACKAGE: "imports the package",
    LOCAL_ONLY: "imports local code only",
    NEITHER: "imports neither",
}


def _to_dict(report: RepoReport) -> dict:
    return {
        "tool": "claim-audit",
        "version": __version__,
        "check": "import-provenance",
        "repo": report.repo,
        "package": report.package,
        "package_roots": report.package_roots,
        "counts": report.counts(),
        "scripts": [
            {
                "path": s.path,
                "classification": s.classification,
                "parse_error": s.parse_error,
                "path_insert_unused": s.path_insert_unused,
                "mutates_sys_path": s.mutates_sys_path,
                "dead_imports": [
                    {"module": d.module, "names": list(d.bound), "line": d.lineno}
                    for d in s.dead
                ],
                "imports": [
                    {
                        "module": i.module,
                        "line": i.lineno,
                        "kind": i.kind,
                        "resolved": i.resolved.as_posix() if i.resolved else None,
                    }
                    for i in s.imports
                ],
            }
            for s in report.scripts
        ],
    }


def _render_text(report: RepoReport) -> str:
    counts = report.counts()
    total = len(report.scripts)
    lines = [
        f"repo:    {report.repo}",
        f"package: {report.package or '(not found)'}"
        + (f"  roots: {', '.join(report.package_roots)}" if report.package_roots else ""),
        f"scripts: {total}",
        "",
        f"  {counts[PACKAGE]:>4}  {LABELS[PACKAGE]}",
        f"  {counts[LOCAL_ONLY]:>4}  {LABELS[LOCAL_ONLY]}",
        f"  {counts[NEITHER]:>4}  {LABELS[NEITHER]}",
    ]

    if report.package is None or not report.package_roots:
        lines += [
            "",
            "note: no importable package was found for this repository. Every script will",
            "      classify as local_only or neither. Pass --package to name it explicitly.",
        ]

    def section(title: str, rows: list[str]) -> None:
        if rows:
            lines.extend(["", title])
            lines.extend(rows)

    section(
        f"scripts importing neither ({counts[NEITHER]}):",
        [f"  {s.path}" for s in report.scripts if s.classification == NEITHER],
    )
    section(
        "sys.path mutated, nothing in this repo imported:",
        [
            f"  {s.path}:{','.join(str(n) for n in s.mutates_sys_path)}"
            for s in report.scripts
            if s.path_insert_unused
        ],
    )
    section(
        "imported and never used:",
        [
            f"  {s.path}:{d.lineno}  {d.module} -> {', '.join(d.bound)}"
            for s in report.scripts
            for d in s.dead
            if d.kind in {"package", "local"}
        ],
    )
    section(
        "not parsed:",
        [f"  {s.path}  {s.parse_error}" for s in report.scripts if s.parse_error],
    )

    lines += [
        "",
        "A flag is a question, not a verdict. Scripts legitimately import neither -",
        "baselines, plotting, data prep. It matters when a published result is",
        "attributed to the package and produced by a script that never loads it.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claim-audit",
        description="Does a script import the package the repository is named for?",
    )
    parser.add_argument("repo", type=Path, help="path to the repository")
    parser.add_argument(
        "--package",
        help="dotted package name to look for (default: from pyproject.toml, then dir name)",
    )
    parser.add_argument(
        "--scripts",
        action="append",
        metavar="GLOB",
        help=f"glob of scripts to analyse, repeatable (default: {', '.join(DEFAULT_SCRIPTS)})",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        metavar="GLOB",
        help=f"glob to skip, repeatable (default: {', '.join(DEFAULT_EXCLUDE)})",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--version", action="version", version=f"claim-audit {__version__}")
    args = parser.parse_args(argv)

    if not args.repo.is_dir():
        parser.error(f"not a directory: {args.repo}")

    report = analyse_repo(args.repo, args.package, args.scripts, args.exclude)

    if args.json:
        print(json.dumps(_to_dict(report), indent=2))
    else:
        print(_render_text(report))

    # Exit 0 regardless of findings. Findings are questions for a human, not failures;
    # a nonzero exit would invite CI to treat them as a gate, which is the wrong shape.
    return 0


if __name__ == "__main__":
    sys.exit(main())
