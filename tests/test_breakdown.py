"""breakdown-sums. Most of these assert that it stays quiet."""

from __future__ import annotations

from pathlib import Path

from claim_audit import breakdown

from tests.test_provenance import write


def run(tmp_path: Path, markdown: str):
    write(tmp_path, "README.md", markdown)
    return breakdown.run(tmp_path).findings


def test_mismatched_total_flagged(tmp_path: Path):
    findings = run(
        tmp_path,
        "| category | scripts |\n| --- | --- |\n"
        "| package | 18 |\n| harness | 16 |\n| neither | 17 |\n| Total | 55 |\n",
    )
    assert len(findings) == 1
    assert findings[0].rule == "breakdown-sums"
    assert "51" in findings[0].evidence[1]
    assert "55" in findings[0].evidence[2]


def test_correct_total_silent(tmp_path: Path):
    assert (
        run(
            tmp_path,
            "| category | scripts |\n| --- | --- |\n"
            "| package | 18 |\n| harness | 16 |\n| neither | 17 |\n| Total | 51 |\n",
        )
        == []
    )


def test_no_total_row_silent(tmp_path: Path):
    assert run(tmp_path, "| a | n |\n| --- | --- |\n| x | 1 |\n| y | 2 |\n") == []


def test_two_total_rows_silent(tmp_path: Path):
    """Nested subtotals — summing every non-total row is the wrong arithmetic."""
    assert (
        run(
            tmp_path,
            "| group | n |\n| --- | --- |\n| a | 1 |\n| Subtotal | 1 |\n"
            "| b | 2 |\n| Total | 3 |\n",
        )
        == []
    )


def test_percentage_column_skipped(tmp_path: Path):
    """Percentages of overlapping sets legitimately exceed 100."""
    assert (
        run(
            tmp_path,
            "| category | % |\n| --- | --- |\n| a | 60 |\n| b | 60 |\n| Total | 100 |\n",
        )
        == []
    )


def test_non_integer_cells_skipped(tmp_path: Path):
    assert (
        run(
            tmp_path,
            "| category | score |\n| --- | --- |\n| a | 0.5 |\n| b | 0.25 |\n| Total | 1.0 |\n",
        )
        == []
    )


def test_blank_cell_skipped(tmp_path: Path):
    assert (
        run(
            tmp_path,
            "| category | n |\n| --- | --- |\n| a | 1 |\n| b |  |\n| Total | 5 |\n",
        )
        == []
    )


def test_single_part_row_skipped(tmp_path: Path):
    assert run(tmp_path, "| a | n |\n| --- | --- |\n| x | 1 |\n| Total | 9 |\n") == []


def test_thousands_separators_parsed(tmp_path: Path):
    findings = run(
        tmp_path,
        "| a | n |\n| --- | --- |\n| x | 1,000 |\n| y | 2,000 |\n| Total | 3,001 |\n",
    )
    assert len(findings) == 1


def test_bold_total_label_recognised(tmp_path: Path):
    findings = run(
        tmp_path,
        "| a | n |\n| --- | --- |\n| x | 1 |\n| y | 2 |\n| **Total** | 4 |\n",
    )
    assert len(findings) == 1


def test_table_inside_code_fence_ignored(tmp_path: Path):
    assert (
        run(
            tmp_path,
            "```\n| a | n |\n| --- | --- |\n| x | 1 |\n| y | 2 |\n| Total | 9 |\n```\n",
        )
        == []
    )


def test_multiple_columns_checked_independently(tmp_path: Path):
    findings = run(
        tmp_path,
        "| a | n | m |\n| --- | --- | --- |\n| x | 1 | 1 |\n| y | 2 | 2 |\n| Total | 3 | 9 |\n",
    )
    assert len(findings) == 1
    assert '"m"' in findings[0].evidence[0]
