"""The one shape every check emits.

SPEC §5: a flag is a question, not a verdict. That is enforced structurally here rather
than left to each check's prose — a Finding carries a location, the rule that fired, the
evidence, and a question. There is no field for a severity, a score, or a judgement about
intent, because there is nothing any of these checks could put in one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIER_A = "A"
TIER_ONLINE = "online"
"""Not a tier. Network-dependent checks are reported separately and never counted as
Tier A facts — see SPEC amendment A1."""


@dataclass(frozen=True)
class Finding:
    rule: str
    """Check name, e.g. "breakdown-sums"."""
    path: str
    """Repo-relative, forward-slashed."""
    line: int | None
    evidence: tuple[str, ...]
    """What was observed. Facts only, no inference."""
    question: str
    """What a human is being asked to determine. Always a question."""
    tier: str = TIER_A

    def render(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        lines = [f"{where}  {self.rule}"]
        lines += [f"    {e}" for e in self.evidence]
        lines.append(f"    -> {self.question}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "tier": self.tier,
            "path": self.path,
            "line": self.line,
            "evidence": list(self.evidence),
            "question": self.question,
        }


@dataclass
class CheckResult:
    """What one check saw, including how much it looked at.

    `examined` is not decoration. A check that fired zero times because it found nothing
    and a check that fired zero times because it was handed no files are different
    results, and SPEC §7 requires reporting what did *not* fire.
    """

    rule: str
    findings: list[Finding] = field(default_factory=list)
    examined: int = 0
    tier: str = TIER_A
    note: str | None = None
    """Why this check could not run, or ran degraded. Shown to the user."""
