# claim-audit — spec

A static analyser for research repositories that flags **claim/evidence gaps**: places where a
published number is not traceable to code that could have produced it.

Derived from a manual audit of seven repositories (2026-09-08/09), recorded in
`~/code/CLAIM-AUDIT-LOG.md`. That audit found eleven distinct failure modes and, for most of them,
a *mechanical tell* — a pattern in the source that a machine can find. This project tests whether
those tells are real detectors or post-hoc rationalisations.

---

## 1. The claim under test

> The failure modes found by hand in seven repositories have mechanical tells that generalise to
> repositories the auditor has never seen.

Not "this tool finds problems." Any grep finds problems. The claim is about **transfer**.

## 2. The result that could come out at zero

Out-of-sample precision. The tells were derived from seven repos, all Jason's, all labelled by the
same process that is now proposing to automate itself. That is a textbook overfitting setup, and
the honest prior is that precision drops substantially off the derivation set.

**The primary reported number is precision on repositories that were never manually audited.** If
that comes in near the base rate of "any flag a reviewer would have raised anyway," the tells are
descriptions of seven specific incidents and not detectors. That is a real, publishable null, and
it is the most likely single outcome.

Pre-registered before any code runs:

- Primary metric: out-of-sample precision, per check, with a Wilson interval.
- Success threshold: no threshold. There is no bar to clear; the number is the result.
- The tool ships with whatever precision it has, including bad, and the README reports it.

## 3. Corpus and labels

### 3.1 Derivation set (labelled, n=7)

`CLAIM-AUDIT-LOG.md` labels seven repos with file:line evidence. Its labels **predate any
detector**, which is the one genuinely strong property of this dataset — the labels cannot have
been written to fit the tool.

| Repo | Modes labelled | Role |
|---|---|---|
| `Mellifera-app` | 2 | positive |
| `agentic-pr` | 1, 2, 8 | positive (private — see §7) |
| `collaborative-nested-learning` | — (one coverage overclaim) | **negative control** |
| `aegis` | 3 | positive |
| `doc-understanding` | 1 | positive |
| `strategy-tournament` | 4 | positive (repo absent) |
| `GCL` | 5, 6, 7, 9, 10, 11 | positive |

### 3.2 The limitation that shapes everything downstream

**Most modes have n = 1.** Mode 4 was found once. Mode 8 was found once. Mode 11 was found once.
Per-mode recall is not estimable from this corpus and will not be reported as though it were.

Consequences, accepted up front:

- The derivation set can measure **precision** (does a flag correspond to something a reviewer
  confirms?). It cannot measure **recall** without labelling repos nobody has audited.
- Any per-mode statistic with n < 5 is reported as a raw count and a list of instances, never as a
  rate, never with a confidence interval. A CI on n=1 is the exact error this project exists to
  detect (see mode 11, and `headlineStats.ts`'s note on why some figures are excluded from the
  numeral guard).
- One negative control is one negative control. It bounds nothing.

### 3.3 Out-of-sample set (unlabelled, to be built)

30–50 public research repositories, sampled from Papers-with-Code / arXiv-linked GitHub, filtered
to: Python, has a README with numeric claims, has something resembling a results artifact.

Labelling protocol, fixed before running the tool:

1. Run the tool. Record all flags. **Do not look at them.**
2. Hand-audit a random sample of *n* repos blind to the tool's output, using the method in
   `CLAIM-AUDIT-LOG.md` ("Audit method that worked").
3. Unseal. Compute precision (flags confirmed / flags raised) and the confirmed-misses list.

Step 2 is the expensive part and the whole experiment. Budget accordingly; a smaller blind sample
honestly labelled beats a larger one labelled after seeing flags.

## 4. Checks, tiered by decidability

Not all eleven modes are equally machine-findable. Tiering this honestly is a design requirement,
not a caveat — a tool that presents a heuristic and a fact with the same confidence is committing
mode 7 (a real signal authenticating a speculative one).

### Tier A — decidable. These are facts, not heuristics. False positives should be ~0.

| Check | Mode | Rule |
|---|---|---|
| `import-provenance` | 9 | A script under `experiments/`/`benchmarks/` that does not import the package the repo is named for. Report the import graph, not a verdict. |
| `dead-import` | 9 | A name is imported and never appears in a call/attribute position. |
| `path-insert-unused` | 9 | `sys.path.insert` with no subsequent import resolving through it. |
| `link-resolves` | 4, 8 | Every GitHub URL and every `file:line` cited in docs resolves publicly (unauthenticated fetch). |
| `numeral-has-source` | 7 | Every numeral in README/docs prose has a counterpart in some results artifact or source literal. Report orphans. |
| `breakdown-sums` | 3 | Markdown tables whose rows are counts and whose caption/header implies a total: do the parts sum to the whole? |

`import-provenance` alone found three live failures across two repos during the manual audit. It
ships first, standalone, before any of the rest exists.

### Tier B — strong heuristics. Real false-positive rate. Must be measured, not assumed.

| Check | Mode | Rule |
|---|---|---|
| `stub-predictor` | 2 | A function whose name matches `predict\|score\|classify\|infer\|forecast` whose only return path derives from an RNG call. |
| `synthetic-to-stats` | 5 | AST dataflow: a value from `np.random.*`/`random.*` reaches a `scipy.stats.*` call without passing through file I/O or a model. |
| `circular-fit` | 10 | A literal functional form (`np.log`, `np.exp`, `**`) appears in a generator expression, and a fit (`linregress`, `curve_fit`, `polyfit`) is later applied to the same variable. |
| `constant-sweep` | — | A results artifact where a metric has `std == 0.0` across a sweep, or is identical across all cells. |
| `symmetric-bounds` | 11 | Swept results whose extremes are exactly ±equal. Construction artifact until shown otherwise. |
| `plan-language` | 1 | A numeral appearing in a doc under a heading matching `plan\|estimate\|target\|proposal\|roadmap` **and** in a results/README context. |

### Tier C — not mechanically decidable. Out of scope for v1; documented so nobody thinks the tool covers them.

- **Mode 6** (a partial correction lending credibility to uncorrected material next to it) — requires
  knowing what *should* have been corrected.
- **Mode 11 in general** (two functions that reduce to the same thing) — undecidable statically.
  `symmetric-bounds` is a narrow proxy for one of its symptoms, not a detector for the mode.
- **Selective comparison** (a true number inside a chosen subset, e.g. "97% of MARL") — requires
  knowing the unchosen baselines mattered.

The README states plainly that Tier C exists and that a clean run does not mean a clean repo.

## 5. What a flag means

A flag is **a question, not a verdict.** Output format is a location, the rule that fired, and the
evidence — never a judgement about intent.

```
GCL/experiments/40_corrected_oracle.py:35  path-insert-unused
  sys.path.insert(...) adds <repo>/ to sys.path
  No import in this file resolves through it.
  → Does this experiment run the package it is named for?
```

Precision is therefore defined as: **of flags raised, how many did a blind human reviewer confirm
as a real claim/evidence gap?** Not "how many are bugs." A dead import is not a bug; it is evidence
that a published finding may describe a different system than its heading says.

## 6. Phases

1. **`import-provenance`, standalone.** Python AST walk, JSON + human output, run against all seven
   labelled repos. Must reproduce the manual finding (GCL: 18 import `src/gcl/`, 16 harness-only, 17
   neither) exactly. If it doesn't, the checker is wrong, not the log.
2. **Tier A, complete.** Plus the negative control run on CNL. Any Tier A flag on CNL is
   investigated as a tool bug before it is reported as a finding.
3. **Tier B.** Each check measured on the derivation set for precision before it is enabled by
   default. Checks that fire on CNL ship disabled.
4. **Out-of-sample study.** §3.3 protocol. This is the actual experiment; 1–3 are instrumentation.
5. **CI.** Weekly run against a pinned corpus, artifact committed with `commit_sha` and
   `workflow_run_url`. Copy CNL's `benchmarks/` + `ci_results/latest.json` pattern verbatim — it is
   the only claim on the whole site that survived being audited.

## 7. Constraints that keep this from becoming what it detects

Written now, while it is cheap to honour.

- **No check may hardcode the thing it reports discovering** (mode 10). The tell taxonomy lives in
  data (`checks/*.yaml`), not in the metric that scores it.
- **The tool must run the corpus it claims to analyse** (mode 9). No `sys.path.insert` to nothing.
  `import-provenance` is run against `claim-audit` itself in CI, and its own output is committed.
- **No statistic on n < 5** (mode 11 / §3.2). Enforced in the reporting code, not by convention.
- **Report what did not fire.** A results artifact listing only hits is a selective comparison
  (mode 6). Every run emits checks-run, checks-fired, and checks-skipped-and-why.
- **`agentic-pr` is private and stays private** (mode 8, and Jason's standing decision). It is
  excluded from any published corpus. Its labels may inform check design; its results may not be
  cited as evidence a reader cannot verify. If it is needed for a number, that number does not get
  published.
- **The negative control is load-bearing.** If CNL ever stops being clean, either CNL regressed or
  the tool did. Both are findings; neither is silent.

## 8. Pre-registered limitations

To go in the README from the first commit, not added later:

1. Eleven modes derived from seven repositories, all written or commissioned by one person. The
   sample is small and not independent.
2. Most modes have n = 1. Recall is unmeasured and, on this corpus, unmeasurable.
3. The labels and the checks were produced by the same agent. The blind out-of-sample protocol
   (§3.3) is the only thing standing between this and circularity, and it depends on the auditor
   actually not peeking.
4. Python only. The manual audit found mode 2 in JavaScript (`Math.random()` in
   `server/mlModel.js`) and mode 1 in TypeScript. v1 will not catch either.
5. Tier C modes are undetected and include the two subtlest ones found by hand.
6. A clean run means no tell fired. It does not mean the claims are true.

---

## Open decisions for Jason

- **Name.** `claim-audit` matches the existing log file. Say if you want something else before
  there's a remote.
- **Public or private.** Recommend public, and early — the value proposition is that other people
  can check it, and a private repo carrying an honesty tool is mode 8 in one move.
- **Out-of-sample corpus.** Public research repos means publishing flags on other people's work.
  Recommend flags-as-questions framing, no repo named in the headline result, and the corpus list
  published so the sample isn't cherry-picked. Your call — it's the one irreversible-ish choice
  here.
