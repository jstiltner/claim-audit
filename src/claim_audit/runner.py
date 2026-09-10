"""Runs the checks and holds the result of a whole audit."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from claim_audit import breakdown, numerals, online, refs
from claim_audit.finding import TIER_A, CheckResult, Finding
from claim_audit.provenance import NEITHER, RepoReport, analyse_repo

PROVENANCE_RULES = ("path-insert-unused", "dead-import")


def provenance_findings(report: RepoReport) -> CheckResult:
    """The two derived facts from import provenance, as Findings.

    The three-way classification itself is not a finding — most `neither` scripts are
    legitimate, and emitting one per script would bury the two facts that do mean
    something.
    """
    result = CheckResult(rule="import-provenance", examined=len(report.scripts))
    for script in report.scripts:
        if script.path_insert_unused:
            lines = ", ".join(str(n) for n in script.mutates_sys_path)
            result.findings.append(
                Finding(
                    rule="path-insert-unused",
                    path=script.path,
                    line=script.mutates_sys_path[0],
                    evidence=(
                        f"Mutates sys.path at line {lines}.",
                        "No import in this file resolves to anything inside this repository.",
                    ),
                    question="Does this script run the package it is named for?",
                )
            )
        for dead in script.dead:
            if dead.kind not in ("package", "local"):
                continue
            result.findings.append(
                Finding(
                    rule="dead-import",
                    path=script.path,
                    line=dead.lineno,
                    evidence=(
                        f"Imports {', '.join(dead.bound)} from `{dead.module}`.",
                        "The name is never referenced again in this file.",
                    ),
                    question=(
                        "Does this script use the module it imports, or reimplement it?"
                    ),
                )
            )
    return result


@dataclass
class Audit:
    repo: str
    provenance: RepoReport
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def tier_a(self) -> list[Finding]:
        return [f for c in self.checks for f in c.findings if f.tier == TIER_A]

    @property
    def other(self) -> list[Finding]:
        return [f for c in self.checks for f in c.findings if f.tier != TIER_A]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for check in self.checks:
            for finding in check.findings:
                out[finding.rule] = out.get(finding.rule, 0) + 1
        return out

    def silent_rules(self) -> list[str]:
        """Checks that ran and found nothing.

        SPEC §7 requires reporting these. A tool that only lists what fired lets a reader
        assume everything else was examined, which is the reporting failure the project is
        about.
        """
        fired = {f.rule for c in self.checks for f in c.findings}
        rules: list[str] = []
        for check in self.checks:
            if check.rule == "import-provenance":
                rules.extend(r for r in PROVENANCE_RULES if r not in fired)
            elif check.rule not in fired:
                rules.append(check.rule)
        return rules


def run(
    repo: Path,
    package: str | None = None,
    scripts: list[str] | None = None,
    exclude: list[str] | None = None,
    docs: list[str] | None = None,
    doc_exclude: list[str] | None = None,
    with_online: bool = False,
) -> Audit:
    repo = repo.resolve()
    report = analyse_repo(repo, package, scripts, exclude)

    checks = [
        provenance_findings(report),
        breakdown.run(repo, docs, doc_exclude),
        refs.run(repo, docs, doc_exclude),
        numerals.run(repo, docs, doc_exclude),
    ]
    if with_online:
        checks.append(online.run(repo, docs, doc_exclude))

    return Audit(repo=repo.name, provenance=report, checks=checks)


__all__ = ["Audit", "run", "provenance_findings", "NEITHER"]
