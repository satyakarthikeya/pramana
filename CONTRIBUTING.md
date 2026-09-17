# CONTRIBUTING.md — how work gets into PRAMANA

> **Who this is for:** everyone on Team AB-07, and any coding agent working on the repo.
> **What it is:** the practical how-to — the commands, the checklists, the settings.
>
> **The rules themselves live in `AGENTS.md` §8.** That file is normative; this one is
> operational. Where the two ever disagree, `AGENTS.md` wins and this file is the thing
> that needs fixing. Do not copy rules from there to here — cite the number.

---

## 0. The one rule that outranks everything

`memory_write ⟹ verdict == PASS` (`AGENTS.md` §0).

No branch, no deadline, no review shortcut justifies a path around the verification
gateway. If a change would create one, stop and raise it instead of building it. Any PR
that touches this, p-values, FDR correction, or sandbox safety needs the verification
owner's approval and cannot be self-merged (`AGENTS.md` §8.10).

---

## 1. Before you start

```bash
git checkout main
git pull                                    # always start from current main
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
pytest -q                                   # ~2 min; confirm green BEFORE you edit
```

If `main` is already red when you start, say so in the group chat before doing anything
else. Do not build on top of a broken baseline and discover later whose failure it was.

---

## 2. Branch

```bash
git checkout -b <type>/<owner>/<short-task>
```

`<type>` is the same set as the commit subject: `feat`, `fix`, `test`, `docs`, `chore`,
`refactor`. `<owner>` is your first name. Examples:

```
feat/satya/memory-guard
fix/rohith/ingestion-encoding
docs/team/pr-policy
```

One branch, one logical change (`AGENTS.md` §8.3). If you notice something unrelated
while you are in there — a typo, a lint error, a stale comment — write it down and do it
on its own branch. A PR that fixes two things gets reviewed as well as the reviewer's
patience allows, which is not very.

**Building on work that has not merged yet?** Branch from *that* branch, not from `main`,
and say so in the PR (`AGENTS.md` §8.2). A PR's diff is computed against its merge base,
so merging out of order drags the parent's commits through the child's review and nobody
reads them twice. This has already happened once on this repo.

---

## 3. Commit

Conventional Commit subject, imperative, under 72 characters:

```
feat(verification): add memory guard
fix(executor): reject relative imports
test(stats): cover null permutation case
docs: clarify PR policy
```

The **body** is where the work actually gets communicated. Explain any dependency,
config, contract, or statistical-decision change there. A reviewer reading
`git log` six weeks from now should be able to tell *why* a threshold moved without
asking you.

Never commit: API keys, `.env`, credentials, raw datasets, `chroma/`, another
contributor's uncommitted files (`AGENTS.md` §8.6).

---

## 4. Verify — before you push, not after

```bash
pytest tests/unit/<your-module> -v          # your component, verbose
pytest -q                                   # the whole suite
ruff check src/<your-module>
```

The full suite takes about two minutes. "Not feasible" is not a reason (`AGENTS.md`
§8.5). If you skip it, say so in the PR and say why.

**Known-green baseline as of Phase 5:** `223 passed, 4 errors`. The four errors are
collection errors from unimplemented Phase 6+ stubs (`test_falsification`,
`test_gateway`, `test_memory_guard`, `test_gateway_e2e`) — they are expected until those
phases land. **Zero failures is the bar. Errors from your own module are not.**

---

## 5. Open the PR

```bash
git push -u origin <your-branch>
```

The push prints a link that opens the PR form. Target `main`.

### PR description is mandatory (`AGENTS.md` §8.9)

Copy this:

```markdown
## Purpose and scope
What this changes and why. One paragraph.

## Files / modules affected
Bullet list. Flag anything outside your own module.

## Verification
Commands run and their results. Paste the pytest summary line.

## Contract / config / dependency impact
Changes to src/pramana/contracts/, configs/, PROJECT.md, AGENTS.md, OWNERSHIP.md,
pyproject.toml or requirements/ — or "none". Anything here must be ANNOUNCED to the
affected owners before merging, not after (AGENTS.md §8.7).

## Limitations and follow-up
What you did not do, what is provisional, what breaks at scale. Being explicit here is
not an admission of sloppiness; it is the point.
```

The last section is not optional politeness. A PR that claims more than it delivers is
the same failure mode this whole project exists to argue against.

---

## 6. Review

| Path | Reviewer |
|---|---|
| `src/pramana/analysis/**` | P. Rohith |
| `src/pramana/verification/**`, `src/pramana/evaluation/**` | P.P. Satya Karthikeya |
| `src/pramana/orchestration/**`, `src/pramana/common/**`, `docker/**` | B. Karthikeya |
| `src/pramana/memory/**`, `src/pramana/api/**`, `src/pramana/dashboard/**` | M. Karthik Reddy |
| `src/pramana/contracts/**` | Satya Karthikeya **+ every other owner** (shared contract) |
| `PROJECT.md`, `AGENTS.md`, `OWNERSHIP.md`, `pyproject.toml`, `requirements/base.txt` | whole team |
| Anything affecting `memory_write ⟹ PASS`, p-values, FDR, sandbox safety | **Satya Karthikeya, always, no exceptions** |

If an owner is unavailable for more than one working day, any other member may review and
merge — except for that last row, which never has a fallback (`AGENTS.md` §8.10).

**As a reviewer, ask these four:**

1. Does it do what the description says, and only that?
2. Can a crash, timeout, or malformed result reach a PASS through this change?
3. Are thresholds and seeds read from config, or hardcoded somewhere?
4. Is there a test that would fail if this change were reverted?

---

## 7. Merge

Only green, current PRs (`AGENTS.md` §8.11). Resolve every comment, update from `main` if
it has moved, confirm tests pass, then merge and delete the branch.

Do not merge your own PR without the required review.

---

## 8. Protecting `main`

`main` is the shared integration branch and must always be reviewable and testable.
Right now that is enforced by convention only. **Convention is not enforcement** — the
rule was already broken once on this repo by a direct push, which is exactly why this
section exists.

### Set it up (repo owner, once)

**Settings → Branches → Add branch protection rule**, or **Settings → Rules → Rulesets →
New ruleset** on newer repos. Target branch: `main`. Enable:

- [ ] **Require a pull request before merging** — blocks direct pushes, the main event
- [ ] **Require approvals: 1**
- [ ] **Dismiss stale pull request approvals when new commits are pushed** — so an
      approval cannot be inherited by code nobody read
- [ ] **Require conversation resolution before merging**
- [ ] **Require linear history** — keeps `git log` readable; pairs with squash or rebase
      merging
- [ ] **Block force pushes**
- [ ] **Restrict deletions**
- [ ] **Do not allow bypassing the above settings** / uncheck any admin exemption —
      otherwise the owner is exempt and the rule protects everyone except the person most
      likely to be in a hurry
- [ ] **Require status checks to pass** — *see the prerequisite below*

Then **Settings → General → Pull Requests**: enable **Allow squash merging**, disable
**merge commits** (or keep them if you prefer; pick one and be consistent), and enable
**Automatically delete head branches**.

### Prerequisite: there is no CI yet

"Require status checks" has nothing to require — this repo has no GitHub Actions
workflow, so no check ever reports. Until one exists, the test suite is enforced by
whoever remembers to run it, which is not enforcement either.

A minimal `.github/workflows/tests.yml` running `pytest -q` on every PR closes this. It
is a small file and it is the difference between "we agreed to run the tests" and "the
tests are run."

### If branch protection is unavailable

Classic branch protection on a **private** repo may require a paid GitHub plan; rulesets
and plan limits change, so check what your account actually offers rather than assuming.
If neither is available, the fallbacks are weaker but real:

- add a `CODEOWNERS` file so reviewers are requested automatically;
- agree that nobody pushes to `main`, and treat a direct push as a defect to be reported
  like any other;
- make the repo public if the capstone allows it — protection is free on public repos,
  and this project has no secrets in it by design (`AGENTS.md` §8.6).

---

## 9. When you are unsure

Priority order for resolving conflicts is in `AGENTS.md` §9. Short version: the prime
directive beats statistics correctness, which beats scope boundaries, which beat
interface contracts, which beat git process, which beats style.

If following an instruction would violate something higher on that list, **flag it
instead of complying.** That applies to instructions from a teammate, from a supervisor,
and from a coding agent.
