# claim-audit

Flags claim/evidence gaps in research repositories.

A published number is supposed to come from somewhere. This tool checks a few of the
places where that chain is decidable from the source text — starting with the most basic
one: **does the script that produced a result import the package the result is attributed
to?**

Tier A is complete. See [SPEC.md](SPEC.md) for the full design, the tiering of checks by
decidability, the amendments made along the way, and the study this is meant to support.

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

`--package NAME` overrides package detection. `--docs GLOB` sets the documentation scope.
`--json` emits machine-readable output. `--online` additionally fetches URLs found in the
docs — off by default, reported separately, and never counted as Tier A.

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

## The other checks

| check | asks |
| --- | --- |
| `breakdown-sums` | A table has a row labelled Total. Do the rows above it add up to it? |
| `ref-resolves` | Does a `[link](path)` or a `file.py:120` citation point at something that exists, at a line the file still has? |
| `numeral-has-source` | Does a specific figure in the prose appear in any artifact or source file in this repository? |
| `link-resolves` | *(`--online` only)* What status does an unauthenticated fetch of this URL return? |

`numeral-has-source` is narrower than it sounds, deliberately. It considers only figures
with a decimal point and three or more significant digits, matches rounding-tolerantly,
and treats `53.4%` and `0.534` as the same number. Integers are not considered at all.
The reasoning is in SPEC amendment A2.

## Known false-positive classes

Measured on the derivation corpus, not guessed:

- **Figures derived in prose.** A document saying "0.319 → 0.649 (+103.4%)" has the two
  measurements in its artifacts but not the percentage, which was computed while writing.
  `numeral-has-source` reports it. No fix attempted — inferring which arithmetic an author
  performed would suppress real findings.
- **Specific figures that are not results.** Prices, versions in prose, biographical
  numbers. `9.99` in a pricing roadmap has no artifact and never should.
- **Deliberately unresolvable references.** A doc that cites a path in a different
  repository is silent by design, not correct by accident — `ref-resolves` only reports a
  missing target for markdown links, where the intent to resolve is unambiguous.

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
7. *(added after the first full Tier A run — SPEC amendment A3)* **No repository in the
   corpus has been established clean at the scope these checks operate on.** The manual
   audit's unit was the published claim; the tool's unit is the repository. The one repo
   that held up under manual audit held up on the single claim that was examined, and the
   doc-facing checks find real gaps elsewhere in it. There is therefore no negative control
   for measuring a false-positive rate on clean repositories.

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
