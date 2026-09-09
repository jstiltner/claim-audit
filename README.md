# claim-audit

Flags claim/evidence gaps in research repositories.

A published number is supposed to come from somewhere. This tool checks a few of the
places where that chain is decidable from the source text — starting with the most basic
one: **does the script that produced a result import the package the result is attributed
to?**

Phase 1 ships one check, `import-provenance`. See [SPEC.md](SPEC.md) for the full design,
the tiering of checks by decidability, and the study this is meant to support.

## Where this came from

A manual audit of seven research repositories turned up eleven recurring failure modes.
Most of them have a *mechanical tell*. The claim under test is not "this tool finds
problems" — it is that **tells found by hand in seven repositories generalise to
repositories the auditor has never seen.** That is an empirical claim with a real chance of
coming out at zero, and it has not been measured yet.

## Install

```
pip install -e .
```

Python 3.11+. No dependencies.

## Use

```
claim-audit /path/to/repo
```

Default scope is `experiments/**/*.py` and `benchmarks/**/*.py`. The tool does not guess
what an "experiment" is; narrow or widen it yourself:

```
claim-audit ./GCL \
  --scripts 'experiments/[0-9]*.py' \
  --scripts 'experiments/36_marl_comparison/*.py' \
  --exclude '**/__init__.py'
```

`--package NAME` overrides package detection. `--json` emits machine-readable output.

Exit status is always 0. Findings are questions for a human, not build failures — a
nonzero exit would invite CI to treat them as a gate, which is the wrong shape for
something with a nonzero false-positive rate.

## What it reports

Each script is classified three ways:

| classification | meaning |
| --- | --- |
| `package` | at least one import resolves into the repository's own package |
| `local_only` | no package import, but something resolves elsewhere in the repo — typically a shared harness beside the scripts |
| `neither` | nothing it imports lives in this repository at all |

Plus two derived facts:

- **`sys.path` mutated, nothing in this repo imported.** The file adjusts `sys.path` and
  then imports nothing local. This is deliberately *not* a claim that the inserted path is
  wrong — insert expressions are usually dynamic (`Path(__file__).parent.parent / "src"`)
  and the tool does not evaluate them. It reports the pair of facts that need no
  evaluation.
- **Imported and never used.** A name is imported from inside the repo and never
  referenced again. An import statement is not evidence of use.

## A flag is a question, not a verdict

Plenty of scripts legitimately import neither: baselines, plotting, data prep, ablations
against external libraries. `neither` is not a finding by itself.

It becomes a finding when a *published result* is attributed to the package and was
produced by a script that never loads it. The tool reports the fact. A human supplies the
attribution.

## Pre-registered limitations

Written before the results, and kept here rather than added later:

1. The eleven modes were derived from seven repositories, all written or commissioned by
   one person. The sample is small and not independent.
2. **Most modes have n = 1.** Recall is unmeasured and, on this corpus, unmeasurable. Any
   per-mode statistic with n < 5 is reported as a raw count — never a rate, never with a
   confidence interval. Putting an interval on n=1 is itself one of the eleven modes.
3. The labels and the checks were produced by the same agent. The blind out-of-sample
   protocol (SPEC §3.3 — run the tool, do not look at the flags, hand-audit blind, then
   unseal) is the only thing standing between this and circularity, and it depends on the
   auditor actually not peeking.
4. Python only. The manual audit found failure modes in JavaScript and TypeScript that v1
   will not catch.
5. The subtlest modes found by hand are undetectable by this approach and are documented as
   uncovered (SPEC §4, Tier C), not silently omitted.
6. **A clean run means no tell fired. It does not mean the claims are true.**

### Known gaps in package detection

- Package name is read from `pyproject.toml` `[project].name`, then the directory name,
  then a lone package under `src/`, then `src/` itself if it is a package. Names declared
  only in `setup.py` are not read — pass `--package`.
- Dynamic imports (`importlib`, `__import__`, imports inside `try`/`except ImportError`
  fallbacks) are resolved as ordinary imports if they are written as import statements, and
  missed entirely otherwise.

## Development

```
pip install -e ".[dev]"
pytest
```

The test suite builds every fixture from scratch in a temp directory, so it asserts nothing
about any particular real repository. The real acceptance test is in SPEC §6: reproducing a
hand-counted 18/16/17 provenance split on a repository audited manually. If the tool
disagrees with the hand count, the tool is wrong.
