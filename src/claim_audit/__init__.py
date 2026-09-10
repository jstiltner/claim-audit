"""claim-audit: flags claim/evidence gaps in research repositories.

Tier A is complete: import provenance and its two derived facts, breakdown-sums,
ref-resolves and numeral-has-source. See SPEC.md for the check inventory, the tiering, and
the Tier C modes this tool does not attempt at all.
"""

from __future__ import annotations

__version__ = "0.2.0"

from claim_audit.finding import CheckResult, Finding
from claim_audit.provenance import (
    LOCAL_ONLY,
    NEITHER,
    PACKAGE,
    Import,
    RepoReport,
    ScriptReport,
    analyse_repo,
)

__all__ = [
    "PACKAGE",
    "LOCAL_ONLY",
    "NEITHER",
    "Import",
    "ScriptReport",
    "RepoReport",
    "Finding",
    "CheckResult",
    "analyse_repo",
    "__version__",
]
