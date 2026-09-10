"""numeral-has-source, in its narrowed form (SPEC amendment A1).

The suppression tests carry more weight than the detection test. The broad version of this
check was dropped precisely because it would fire on these cases.
"""

from __future__ import annotations

from pathlib import Path

from claim_audit import numerals

from tests.test_provenance import write


def run(tmp_path: Path, markdown: str, artifact: str = '{"accuracy": 0.534}'):
    write(tmp_path, "README.md", markdown)
    write(tmp_path, "results/latest.json", artifact)
    return numerals.run(tmp_path).findings


def test_orphan_figure_flagged(tmp_path: Path):
    findings = run(tmp_path, "The model reached 0.871 accuracy.\n")
    assert len(findings) == 1
    assert "0.871" in findings[0].evidence[0]


def test_figure_present_in_artifact_silent(tmp_path: Path):
    assert run(tmp_path, "The model reached 0.534 accuracy.\n") == []


def test_rounded_figure_silent(tmp_path: Path):
    """Prose rounds. 0.534 written as 0.53 is the same number, not an orphan."""
    assert run(tmp_path, "The model reached 0.53 accuracy.\n") == []


def test_percentage_of_a_fraction_silent(tmp_path: Path):
    """53.4% and 0.534 are the same number written for different readers."""
    assert run(tmp_path, "The model reached 53.4% accuracy.\n") == []


def test_fraction_of_a_percentage_silent(tmp_path: Path):
    assert run(tmp_path, "A score of 0.534.\n", artifact='{"pct": 53.4}') == []


def test_source_literal_counts_as_a_source(tmp_path: Path):
    write(tmp_path, "src/model.py", "THRESHOLD = 0.871\n")
    assert run(tmp_path, "The threshold is 0.871.\n") == []


def test_years_ignored(tmp_path: Path):
    assert run(tmp_path, "Audited in 2026, revised 1999.\n") == []


def test_versions_ignored(tmp_path: Path):
    assert run(tmp_path, "Requires Python 3.11 and v2.4 of the runner.\n") == []


def test_section_and_figure_references_ignored(tmp_path: Path):
    assert run(tmp_path, "See Section 4.2, Figure 7.1, and Experiment 40.1.\n") == []


def test_issue_numbers_ignored(tmp_path: Path):
    assert run(tmp_path, "Fixed in #1234 and PR 5678.\n") == []


def test_dates_ignored(tmp_path: Path):
    assert run(tmp_path, "Recorded 2026-09-09 in the log.\n") == []


def test_low_specificity_integers_ignored(tmp_path: Path):
    """18 / 16 / 17 are not specific enough for their absence to mean anything."""
    assert run(tmp_path, "Of these, 18 import the package and 16 do not.\n") == []


def test_inline_code_ignored(tmp_path: Path):
    assert run(tmp_path, "Set `alpha = 0.912` in the config.\n") == []


def test_code_fence_ignored(tmp_path: Path):
    assert run(tmp_path, "```\naccuracy = 0.912\n```\n") == []


def test_url_digits_ignored(tmp_path: Path):
    assert run(tmp_path, "See https://example.com/runs/91234/summary for detail.\n") == []


def test_markdown_table_figures_are_checked(tmp_path: Path):
    findings = run(tmp_path, "| model | score |\n| --- | --- |\n| a | 0.912 |\n")
    assert len(findings) == 1


def test_no_artifacts_means_skipped_not_all_orphans(tmp_path: Path):
    """A repo with nothing to trace to yields a note, not a page of findings."""
    write(tmp_path, "README.md", "The model reached 0.871 accuracy.\n")
    result = numerals.run(tmp_path)
    assert result.findings == []
    assert result.note is not None


def test_prose_cannot_be_its_own_source(tmp_path: Path):
    write(tmp_path, "docs/notes.md", "We measured 0.871.\n")
    findings = run(tmp_path, "The model reached 0.871 accuracy.\n")
    assert len(findings) == 1
    assert "docs/notes.md:1" in findings[0].evidence[2]


def test_repeated_orphan_is_one_finding(tmp_path: Path):
    """One untraceable figure repeated across docs is one gap, not many."""
    write(tmp_path, "docs/a.md", "Accuracy was 0.912.\n")
    write(tmp_path, "docs/b.md", "Accuracy was 0.912.\n")
    findings = run(tmp_path, "Accuracy was 0.912.\n")
    assert len(findings) == 1
    assert "Also at" in findings[0].evidence[2]


def test_integers_not_considered(tmp_path: Path):
    """Amendment A2: an integer's absence is too weak to report."""
    assert run(tmp_path, "Deployed across 190 hospitals; the suite has 109 tests.\n") == []
