"""Import provenance: does a script import the package it claims to be about?

This is a Tier A check (see SPEC.md §4). Everything here is a decidable fact about the
source text — which modules a file imports, whether those modules resolve to files inside
the repository, and whether an imported name is ever used. No heuristics, no scoring.

The question it answers, and the only one it answers:

    Does this script import the package this repository is named for?

A "no" is not a finding by itself. Plenty of scripts legitimately don't (baselines,
plotting, data prep). It is a finding when a *published result* is attributed to the
package and produced by a script that never loads it. The tool reports the fact; a human
supplies the attribution.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# "package": at least one import resolves into the repo's own package.
# "local_only": no package import, but something resolves elsewhere inside the repo —
#     typically a shared harness living beside the scripts. The script runs *a* local
#     model, just not the packaged one.
# "neither": nothing this file imports lives in this repository at all. Standalone.
Classification = str
PACKAGE: Classification = "package"
LOCAL_ONLY: Classification = "local_only"
NEITHER: Classification = "neither"

# Where an import resolved to.
KIND_PACKAGE = "package"
KIND_LOCAL = "local"
KIND_STDLIB = "stdlib"
KIND_EXTERNAL = "external"


@dataclass(frozen=True)
class Import:
    """One imported module and the names it binds."""

    module: str
    """Dotted module path as written. `from a.b import c` -> "a.b"."""
    bound: tuple[str, ...]
    """Names this statement introduces into the namespace."""
    lineno: int
    kind: str
    resolved: Path | None
    """Repo-relative path the module resolved to, when it resolved inside the repo."""
    star: bool = False
    """`from x import *` — bindings are untrackable, so dead-import analysis skips it."""


@dataclass
class ScriptReport:
    path: str
    """Repo-relative, forward-slashed."""
    classification: Classification
    imports: list[Import] = field(default_factory=list)
    dead: list[Import] = field(default_factory=list)
    """Imported and never referenced anywhere else in the file."""
    mutates_sys_path: list[int] = field(default_factory=list)
    """Line numbers of sys.path.insert / .append calls."""
    parse_error: str | None = None

    @property
    def path_insert_unused(self) -> bool:
        """Mutates sys.path, then imports nothing from inside this repository.

        Stated exactly: this is *not* a claim that the inserted path is wrong, or that we
        evaluated it. Insert expressions are usually dynamic (`Path(__file__).parent.parent`)
        and this check deliberately does not try to evaluate them. It reports the pair of
        facts that need no evaluation — the file adjusts sys.path, and nothing it imports
        lives here.
        """
        return bool(self.mutates_sys_path) and self.classification == NEITHER


@dataclass
class RepoReport:
    repo: str
    package: str | None
    package_roots: list[str]
    scripts: list[ScriptReport] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {PACKAGE: 0, LOCAL_ONLY: 0, NEITHER: 0}
        for s in self.scripts:
            out[s.classification] += 1
        return out


def detect_package(repo: Path, override: str | None = None) -> tuple[str | None, list[Path]]:
    """Find the importable package this repository is named for.

    Returns the dotted name and every directory it lives under. Two roots is normal: a
    `src/` layout means `gcl` is importable both as `gcl` (with src/ on the path) and as
    `src.gcl` (with the repo root on it), and real repositories use both spellings in
    different scripts. Missing one of them was a live bug during the manual audit — a
    `^from gcl` pattern filed `from src.gcl.core.calculus` as standalone, i.e. it reported
    a genuine user of the package as one of the offenders.
    """
    names: list[str] = []
    if override:
        names.append(override)
    else:
        pyproject = repo / "pyproject.toml"
        if pyproject.is_file():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                declared = data.get("project", {}).get("name")
                if declared:
                    names.append(str(declared).replace("-", "_"))
            except (tomllib.TOMLDecodeError, OSError):
                pass
        names.append(repo.name.replace("-", "_"))

    for name in names:
        roots = [d for d in (repo / "src", repo) if (d / name / "__init__.py").is_file()]
        if roots:
            return name, roots

    src = repo / "src"

    # `src/` is sometimes the package itself — `src/__init__.py` present, modules imported
    # as `src.memory`. Without this the detector finds nothing, every script classifies as
    # local_only, and the whole report is quietly meaningless.
    if (src / "__init__.py").is_file():
        return "src", [repo]

    # Fall back to a lone package under src/, whatever it is called.
    if src.is_dir():
        found = [d for d in sorted(src.iterdir()) if (d / "__init__.py").is_file()]
        if len(found) == 1:
            return found[0].name, [src]

    return (names[0] if names else None), []


def _module_candidates(root: Path, dotted: str) -> list[Path]:
    rel = Path(*dotted.split("."))
    return [root / rel.with_suffix(".py"), root / rel / "__init__.py"]


class _Resolver:
    def __init__(self, repo: Path, package: str | None, package_roots: list[Path]):
        self.repo = repo
        self.package = package
        self.package_roots = package_roots
        # Roots an import can resolve against. `src/` is included regardless of layout
        # because scripts routinely insert it onto sys.path at runtime.
        self.roots = [repo, repo / "src"]
        self._stdlib = set(sys.stdlib_module_names)

    def resolve(self, dotted: str) -> tuple[str, Path | None]:
        if not dotted:
            return KIND_EXTERNAL, None

        for root in self.roots:
            for candidate in _module_candidates(root, dotted):
                if candidate.is_file():
                    inside_package = any(
                        candidate.is_relative_to(r / self.package)
                        for r in self.package_roots
                        if self.package
                    )
                    kind = KIND_PACKAGE if inside_package else KIND_LOCAL
                    return kind, candidate

        if dotted.split(".")[0] in self._stdlib:
            return KIND_STDLIB, None
        return KIND_EXTERNAL, None


def _bound_names(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    names = []
    for alias in node.names:
        if alias.name == "*":
            continue
        if alias.asname:
            names.append(alias.asname)
        else:
            # `import os.path` binds "os", not "os.path".
            names.append(alias.name.split(".")[0])
    return tuple(names)


def _mutates_sys_path(tree: ast.AST) -> list[int]:
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"insert", "append", "extend"}:
            continue
        target = node.func.value
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "path"
            and isinstance(target.value, ast.Name)
            and target.value.id == "sys"
        ):
            lines.append(node.lineno)
    return sorted(lines)


def _used_names(tree: ast.AST, source: str, import_lines: set[int]) -> set[str]:
    """Every identifier that could count as a use of an imported name.

    AST loads are the real signal. The regex pass over non-import lines is a deliberate
    over-approximation on top: it also counts identifiers in comments, docstrings and
    string annotations. That direction is the safe one — it can only *suppress* a
    dead-import flag, never create one. Tier A promises approximately zero false
    positives, and this is how that promise is paid for.
    """
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used.add(base.id)

    for lineno, line in enumerate(source.splitlines(), start=1):
        if lineno in import_lines:
            continue
        used.update(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", line))

    return used


def analyse_script(path: Path, repo: Path, resolver: _Resolver) -> ScriptReport:
    rel = path.relative_to(repo).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        return ScriptReport(path=rel, classification=NEITHER, parse_error=str(exc))

    imports: list[Import] = []
    import_lines: set[int] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                kind, resolved = resolver.resolve(alias.name)
                imports.append(
                    Import(
                        module=alias.name,
                        bound=(alias.asname or alias.name.split(".")[0],),
                        lineno=node.lineno,
                        kind=kind,
                        resolved=resolved,
                    )
                )
            import_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        elif isinstance(node, ast.ImportFrom):
            # Relative imports (level > 0) resolve against the file's own package.
            if node.level:
                base = path.parent
                for _ in range(node.level - 1):
                    base = base.parent
                dotted_parts = base.relative_to(repo).parts + tuple(
                    (node.module or "").split(".") if node.module else ()
                )
                dotted = ".".join(p for p in dotted_parts if p)
            else:
                dotted = node.module or ""
            kind, resolved = resolver.resolve(dotted)
            star = any(a.name == "*" for a in node.names)
            imports.append(
                Import(
                    module=dotted,
                    bound=_bound_names(node),
                    lineno=node.lineno,
                    kind=kind,
                    resolved=resolved,
                    star=star,
                )
            )
            import_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))

    kinds = {i.kind for i in imports}
    if KIND_PACKAGE in kinds:
        classification = PACKAGE
    elif KIND_LOCAL in kinds:
        classification = LOCAL_ONLY
    else:
        classification = NEITHER

    used = _used_names(tree, source, import_lines)
    dead = [
        imp
        for imp in imports
        if not imp.star and imp.bound and all(name not in used for name in imp.bound)
    ]

    return ScriptReport(
        path=rel,
        classification=classification,
        imports=imports,
        dead=dead,
        mutates_sys_path=_mutates_sys_path(tree),
    )


DEFAULT_SCRIPTS = ("experiments/**/*.py", "benchmarks/**/*.py")
DEFAULT_EXCLUDE = ("**/__init__.py", "**/__pycache__/**", "**/.venv/**")


def collect_scripts(
    repo: Path, patterns: list[str], exclude: list[str]
) -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in patterns:
        for match in sorted(repo.glob(pattern)):
            if not match.is_file() or match.suffix != ".py":
                continue
            if any(match.match(x) or match.relative_to(repo).match(x) for x in exclude):
                continue
            seen[match] = None
    return list(seen)


def analyse_repo(
    repo: Path,
    package: str | None = None,
    scripts: list[str] | None = None,
    exclude: list[str] | None = None,
) -> RepoReport:
    repo = repo.resolve()
    name, roots = detect_package(repo, package)
    resolver = _Resolver(repo, name, roots)
    paths = collect_scripts(
        repo, list(scripts or DEFAULT_SCRIPTS), list(exclude or DEFAULT_EXCLUDE)
    )
    return RepoReport(
        repo=repo.name,
        package=name,
        package_roots=[r.relative_to(repo).as_posix() or "." for r in roots],
        scripts=[analyse_script(p, repo, resolver) for p in paths],
    )
