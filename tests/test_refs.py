"""ref-resolves. The interesting assertions are the silences."""

from __future__ import annotations

from pathlib import Path

from claim_audit import refs

from tests.test_provenance import write


def run(tmp_path: Path, markdown: str, doc: str = "README.md"):
    write(tmp_path, doc, markdown)
    return refs.run(tmp_path).findings


def test_broken_relative_link_flagged(tmp_path: Path):
    findings = run(tmp_path, "See [the runner](experiments/run.py).\n")
    assert len(findings) == 1
    assert "experiments/run.py" in findings[0].evidence[0]


def test_existing_relative_link_silent(tmp_path: Path):
    write(tmp_path, "experiments/run.py", "print(1)\n")
    assert run(tmp_path, "See [the runner](experiments/run.py).\n") == []


def test_link_resolved_relative_to_the_doc(tmp_path: Path):
    write(tmp_path, "docs/notes.md", "See [sibling](other.md).\n")
    write(tmp_path, "docs/other.md", "hi\n")
    assert refs.run(tmp_path).findings == []


def test_anchor_and_url_links_ignored(tmp_path: Path):
    assert (
        run(
            tmp_path,
            "[a](#section) [b](https://example.com/x) [c](mailto:x@y.z)\n",
        )
        == []
    )


def test_placeholder_paths_ignored(tmp_path: Path):
    assert run(tmp_path, "[cfg](path/to/config.yml) [t](<your-repo>/x.py)\n") == []


def test_link_inside_code_fence_ignored(tmp_path: Path):
    assert run(tmp_path, "```\n[runner](experiments/run.py)\n```\n") == []


def test_citation_past_end_of_file_flagged(tmp_path: Path):
    write(tmp_path, "run.py", "a = 1\nb = 2\n")
    findings = run(tmp_path, "The bug is at `run.py:40`.\n")
    assert len(findings) == 1
    assert "has 2 lines" in findings[0].evidence[1]


def test_citation_within_file_silent(tmp_path: Path):
    write(tmp_path, "run.py", "a = 1\nb = 2\n")
    assert run(tmp_path, "The bug is at `run.py:2`.\n") == []


def test_citation_to_missing_file_is_silent_not_guessed(tmp_path: Path):
    """An unresolvable citation is more often a pointer into another repo than a bug."""
    assert run(tmp_path, "See `elsewhere/thing.py:9`.\n") == []


def test_bare_python_citation_flagged(tmp_path: Path):
    write(tmp_path, "experiments/run.py", "a = 1\n")
    findings = run(tmp_path, "See experiments/run.py:12 for the loop.\n")
    assert len(findings) == 1


def test_link_inside_inline_code_ignored(tmp_path: Path):
    """A doc showing link syntax is not making a reference."""
    assert run(tmp_path, "Write it as `[link](path)` in the table.\n") == []


def test_link_target_with_line_range_resolves(tmp_path: Path):
    """`[auth](src/app.jsx:1-8)` points at a file plus a range, not a file called `...:1-8`."""
    write(tmp_path, "src/app.jsx", "a\nb\nc\nd\ne\nf\ng\nh\ni\n")
    assert run(tmp_path, "See [auth](src/app.jsx:1-8).\n") == []


def test_link_target_with_line_past_end_flagged(tmp_path: Path):
    write(tmp_path, "src/app.jsx", "a\nb\n")
    findings = run(tmp_path, "See [auth](src/app.jsx:40).\n")
    assert len(findings) == 1
    assert "has 2 lines" in findings[0].evidence[1]


def test_link_target_with_line_to_missing_file_flagged(tmp_path: Path):
    findings = run(tmp_path, "See [auth](src/nope.jsx:1-8).\n")
    assert len(findings) == 1
    assert "`src/nope.jsx`" in findings[0].evidence[0]


def test_path_escaping_the_repo_not_resolved(tmp_path: Path):
    outside = tmp_path.parent / "outside.md"
    outside.write_text("x\n", encoding="utf-8")
    findings = run(tmp_path, "[up](../outside.md)\n")
    assert len(findings) == 1
