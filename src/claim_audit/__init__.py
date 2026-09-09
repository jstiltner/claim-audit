"""claim-audit: flags claim/evidence gaps in research repositories.

Phase 1 covers import provenance only. See SPEC.md for the full check inventory and
for what this tool deliberately does not attempt.
"""

from __future__ import annotations

__version__ = "0.1.0"

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
    "analyse_repo",
    "__version__",
]
