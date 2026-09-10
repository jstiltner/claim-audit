"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from claim_audit import __version__
from claim_audit.docs import DEFAULT_DOCS
from claim_audit.finding import TIER_A
from claim_audit.provenance import (
    DEFAULT_SCRIPTS,
    LOCAL_ONLY,
    NEITHER,
    PACKAGE,
)
from claim_audit.runner import Audit, run

LABELS = {
    PACKAGE: "imports the package",
    LOCAL_ONLY: "imports local code only",
    NEITHER: "imports neither",
}

CLOSING = """A flag is a question, not a verdict. No clean run means the claims are true -
it means no tell fired, and the subtlest failure modes have no tell."""


def _to_dict(audit: Audit) -> dict:
    report = audit.provenance
    return {
        "tool": "claim-audit",
        "version": __version__,
        "repo": report.repo,
        "package": report.package,
        "package_roots": report.package_roots,
        "provenance": {
            "counts": report.counts(),
            "scripts": [
                {
                    "path": s.path,
                    "classification": s.classification,
                    "parse_error": s.parse_error,
                }
                for s in report.scripts
            ],
        },
        "checks": [
            {"rule": c.rule, "tier": c.tier, "examined": c.examined, "note": c.note}
            for c in audit.checks
        ],
        "findings": [f.to_dict() for c in audit.checks for f in c.findings],
        "silent": audit.silent_rules(),
    }


def _render(audit: Audit) -> str:
    report = audit.provenance
    counts = report.counts()
    out = [
        f"repo:    {report.repo}",
        f"package: {report.package or '(not found)'}"
        + (f"  roots: {', '.join(report.package_roots)}" if report.package_roots else ""),
        "",
        "import provenance",
        f"  {counts[PACKAGE]:>4}  {LABELS[PACKAGE]}",
        f"  {counts[LOCAL_ONLY]:>4}  {LABELS[LOCAL_ONLY]}",
        f"  {counts[NEITHER]:>4}  {LABELS[NEITHER]}",
        f"  {len(report.scripts):>4}  scripts examined",
    ]

    if not report.package_roots:
        out += [
            "",
            "  note: no importable package found. Every script will classify as",
            "        local_only or neither, which makes the split above meaningless.",
            "        Pass --package to name it.",
        ]

    tier_a = audit.tier_a
    out += ["", f"Tier A findings ({len(tier_a)}) - facts, not heuristics"]
    if tier_a:
        for finding in tier_a:
            out += ["", "  " + finding.render().replace("\n", "\n  ")]
    else:
        out.append("  none")

    other = audit.other
    if other:
        out += ["", f"Not Tier A ({len(other)}) - network-dependent, reported separately"]
        for finding in other:
            out += ["", "  " + finding.render().replace("\n", "\n  ")]

    notes = [c for c in audit.checks if c.note]
    if notes:
        out += ["", "Checks that could not run fully"]
        out += [f"  {c.rule}: {c.note}" for c in notes]

    silent = audit.silent_rules()
    if silent:
        out += ["", "Ran and found nothing: " + ", ".join(sorted(silent))]

    out += ["", CLOSING]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claim-audit",
        description="Flags claim/evidence gaps in a research repository.",
    )
    parser.add_argument("repo", type=Path, help="path to the repository")
    parser.add_argument(
        "--package",
        help="dotted package name (default: from pyproject.toml, then dir name)",
    )
    parser.add_argument(
        "--scripts",
        action="append",
        metavar="GLOB",
        help=f"scripts to analyse, repeatable (default: {', '.join(DEFAULT_SCRIPTS)})",
    )
    parser.add_argument(
        "--exclude", action="append", metavar="GLOB", help="scripts to skip, repeatable"
    )
    parser.add_argument(
        "--docs",
        action="append",
        metavar="GLOB",
        help=f"docs to analyse, repeatable (default: {', '.join(DEFAULT_DOCS)})",
    )
    parser.add_argument(
        "--doc-exclude", action="append", metavar="GLOB", help="docs to skip, repeatable"
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="also fetch URLs found in docs. Reported separately and never counted as Tier A.",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--version", action="version", version=f"claim-audit {__version__}")
    args = parser.parse_args(argv)

    if not args.repo.is_dir():
        parser.error(f"not a directory: {args.repo}")

    audit = run(
        args.repo,
        package=args.package,
        scripts=args.scripts,
        exclude=args.exclude,
        docs=args.docs,
        doc_exclude=args.doc_exclude,
        with_online=args.online,
    )

    print(json.dumps(_to_dict(audit), indent=2) if args.json else _render(audit))

    # Always 0. Findings are questions for a human, not build failures; a nonzero exit
    # invites CI to treat them as a gate, which is the wrong shape for this.
    return 0


if __name__ == "__main__":
    sys.exit(main())
