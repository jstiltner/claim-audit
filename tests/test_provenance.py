"""Tests for the import-provenance check.

Every fixture here is built from scratch in a tmp_path so the suite says nothing about
any particular real repository. The real-repository acceptance test (GCL's 18/16/17
split) lives in SPEC.md §6 and is run by hand against a checkout the tool does not ship.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claim_audit.cli import main
from claim_audit.provenance import (
    LOCAL_ONLY,
    NEITHER,
    PACKAGE,
    analyse_repo,
    detect_package,
)


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A src-layout repo named `widget`, with a package and a sibling harness."""
    root = tmp_path / "widget"
    write(root, "pyproject.toml", '[project]\nname = "widget"\n')
    write(root, "src/widget/__init__.py", "")
    write(root, "src/widget/core.py", "def run():\n    return 1\n")
    write(root, "experiments/harness/__init__.py", "")
    write(root, "experiments/harness/agent.py", "class Agent:\n    pass\n")
    return root


def only(report, path: str):
    matches = [s for s in report.scripts if s.path == path]
    assert matches, f"{path} not collected; got {[s.path for s in report.scripts]}"
    return matches[0]


def test_detect_package_finds_both_roots(repo: Path):
    """src layout means `widget` and `src.widget` are both live spellings.

    Missing the second root was a real bug during the manual audit: it filed a genuine
    user of the package as a standalone script.
    """
    write(repo, "widget/__init__.py", "")
    name, roots = detect_package(repo)
    assert name == "widget"
    assert {r.name for r in roots} == {"src", "widget"}


def test_package_import_in_either_spelling(repo: Path):
    write(repo, "widget/__init__.py", "")
    write(repo, "widget/core.py", "")
    write(repo, "experiments/a.py", "from widget.core import run\nrun()\n")
    write(repo, "experiments/b.py", "from src.widget.core import run\nrun()\n")

    report = analyse_repo(repo)
    assert only(report, "experiments/a.py").classification == PACKAGE
    assert only(report, "experiments/b.py").classification == PACKAGE


def test_classification_three_ways(repo: Path):
    write(repo, "experiments/uses_package.py", "from widget.core import run\nrun()\n")
    write(
        repo,
        "experiments/uses_harness.py",
        "from experiments.harness.agent import Agent\nAgent()\n",
    )
    write(repo, "experiments/uses_nothing.py", "import json\nimport numpy\nprint(json, numpy)\n")

    # Scoped past the harness itself, which lives under experiments/ and would otherwise
    # be collected and counted as a script in its own right.
    report = analyse_repo(repo, scripts=["experiments/*.py"])
    assert only(report, "experiments/uses_package.py").classification == PACKAGE
    assert only(report, "experiments/uses_harness.py").classification == LOCAL_ONLY
    assert only(report, "experiments/uses_nothing.py").classification == NEITHER
    assert report.counts() == {PACKAGE: 1, LOCAL_ONLY: 1, NEITHER: 1}


def test_package_import_wins_over_local(repo: Path):
    write(
        repo,
        "experiments/both.py",
        "from widget.core import run\nfrom experiments.harness.agent import Agent\nrun()\nAgent()\n",
    )
    assert only(analyse_repo(repo), "experiments/both.py").classification == PACKAGE


def test_import_kinds(repo: Path):
    write(
        repo,
        "experiments/kinds.py",
        "import json\nimport numpy\nimport widget.core\n"
        "from experiments.harness.agent import Agent\n"
        "print(json, numpy, widget, Agent)\n",
    )
    kinds = {i.module: i.kind for i in only(analyse_repo(repo), "experiments/kinds.py").imports}
    assert kinds == {
        "json": "stdlib",
        "numpy": "external",
        "widget.core": "package",
        "experiments.harness.agent": "local",
    }


def test_relative_import_resolves_against_own_package(repo: Path):
    write(repo, "experiments/pkg/__init__.py", "")
    write(repo, "experiments/pkg/helper.py", "VALUE = 1\n")
    write(repo, "experiments/pkg/script.py", "from .helper import VALUE\nprint(VALUE)\n")

    script = only(analyse_repo(repo, scripts=["experiments/**/*.py"]), "experiments/pkg/script.py")
    assert script.classification == LOCAL_ONLY
    assert script.imports[0].module == "experiments.pkg.helper"


# --- dead imports -------------------------------------------------------------------


def test_dead_import_detected(repo: Path):
    """Mode 9's third shape: the import is present, and nothing ever calls it."""
    write(
        repo,
        "experiments/dead.py",
        "from experiments.harness.agent import Agent\n\n"
        "class MyOwnAgent:\n    pass\n\n"
        "MyOwnAgent()\n",
    )
    script = only(analyse_repo(repo), "experiments/dead.py")
    assert [d.bound for d in script.dead] == [("Agent",)]


def test_use_anywhere_suppresses_dead_flag(repo: Path):
    for body in (
        "Agent()",
        "x = Agent",
        "print(Agent.name)",
        "def f(a: Agent): ...",
    ):
        write(repo, "experiments/live.py", f"from experiments.harness.agent import Agent\n{body}\n")
        assert only(analyse_repo(repo), "experiments/live.py").dead == [], body


def test_mention_in_comment_or_string_suppresses_dead_flag(repo: Path):
    """Deliberate over-approximation: it can only suppress a flag, never create one.

    Tier A promises approximately zero false positives, and this is the price.
    """
    write(
        repo,
        "experiments/mentioned.py",
        "from experiments.harness.agent import Agent\n# Agent is constructed by the runner\n",
    )
    assert only(analyse_repo(repo), "experiments/mentioned.py").dead == []


def test_star_import_never_flagged_dead(repo: Path):
    write(repo, "experiments/star.py", "from experiments.harness.agent import *\n")
    script = only(analyse_repo(repo), "experiments/star.py")
    assert script.dead == []
    assert script.classification == LOCAL_ONLY


def test_aliased_and_dotted_bindings(repo: Path):
    write(
        repo,
        "experiments/alias.py",
        "import widget.core as wc\nimport os.path\nprint(wc, os)\n",
    )
    assert only(analyse_repo(repo), "experiments/alias.py").dead == []


# --- sys.path -----------------------------------------------------------------------


def test_path_insert_unused(repo: Path):
    write(
        repo,
        "experiments/inserted.py",
        "import sys\nfrom pathlib import Path\n"
        'sys.path.insert(0, str(Path(__file__).parent.parent / "src"))\n'
        "import numpy\nprint(numpy)\n",
    )
    script = only(analyse_repo(repo), "experiments/inserted.py")
    assert script.mutates_sys_path == [3]
    assert script.classification == NEITHER
    assert script.path_insert_unused is True


def test_path_insert_that_is_used_is_not_flagged(repo: Path):
    write(
        repo,
        "experiments/used.py",
        "import sys\nfrom pathlib import Path\n"
        'sys.path.insert(0, str(Path(__file__).parent.parent / "src"))\n'
        "from widget.core import run\nrun()\n",
    )
    script = only(analyse_repo(repo), "experiments/used.py")
    assert script.mutates_sys_path == [3]
    assert script.path_insert_unused is False


def test_other_list_inserts_are_not_sys_path(repo: Path):
    write(repo, "experiments/other.py", "rows = []\nrows.append(1)\nprint(rows)\n")
    assert only(analyse_repo(repo), "experiments/other.py").mutates_sys_path == []


# --- collection ---------------------------------------------------------------------


def test_syntax_error_is_reported_not_raised(repo: Path):
    write(repo, "experiments/broken.py", "def f(:\n")
    script = only(analyse_repo(repo), "experiments/broken.py")
    assert script.parse_error is not None
    assert script.classification == NEITHER


def test_init_files_excluded_by_default(repo: Path):
    write(repo, "experiments/pkg/__init__.py", "")
    write(repo, "experiments/pkg/script.py", "import json\nprint(json)\n")
    paths = {s.path for s in analyse_repo(repo, scripts=["experiments/pkg/*.py"]).scripts}
    assert paths == {"experiments/pkg/script.py"}


def test_custom_scope(repo: Path):
    write(repo, "experiments/01_a.py", "import json\nprint(json)\n")
    write(repo, "experiments/notes/scratch.py", "import json\nprint(json)\n")
    report = analyse_repo(repo, scripts=["experiments/[0-9]*.py"])
    assert {s.path for s in report.scripts} == {"experiments/01_a.py"}


def test_src_is_itself_the_package(tmp_path: Path):
    """`src/__init__.py` present, modules imported as `src.memory`."""
    root = tmp_path / "nested-learning"
    write(root, "src/__init__.py", "")
    write(root, "src/memory/__init__.py", "")
    write(root, "src/memory/store.py", "class Store:\n    pass\n")
    write(root, "experiments/a.py", "from src.memory.store import Store\nStore()\n")

    name, roots = detect_package(root)
    assert name == "src"
    assert roots == [root]
    assert only(analyse_repo(root), "experiments/a.py").classification == PACKAGE


def test_repo_with_no_package(tmp_path: Path):
    root = tmp_path / "scripts-only"
    write(root, "experiments/a.py", "import json\nprint(json)\n")
    report = analyse_repo(root)
    assert report.package_roots == []
    assert report.counts()[NEITHER] == 1


# --- cli ----------------------------------------------------------------------------


def test_cli_json_output(repo: Path, capsys):
    write(repo, "experiments/a.py", "from widget.core import run\nrun()\n")
    assert main([str(repo), "--json"]) == 0
    payload = capsys.readouterr().out
    assert '"classification": "package"' in payload
    assert '"check": "import-provenance"' in payload


def test_cli_text_output_exits_zero_with_findings(repo: Path, capsys):
    write(repo, "experiments/a.py", "import json\nprint(json)\n")
    assert main([str(repo)]) == 0
    assert "imports neither" in capsys.readouterr().out
