# Repository rulesets

The branch and tag protection for this repository, as JSON. GitHub imports these
files directly, so the settings are versioned, reviewable and restorable instead
of living only in a settings page nobody can diff.

JSON allows no comments — the reasoning is here.

## Applying them

**In the web UI** (no tooling needed):

> Settings → Rules → Rulesets → **New ruleset** → **Import a ruleset** → upload
> `main.json`, then repeat for `release-tags.json`.

**Or with the GitHub CLI**, which reads exactly these files:

```powershell
gh auth login
powershell -ExecutionPolicy Bypass -File .github\setup-repo-rules.ps1
```

**Order matters.** Push `main` first, while direct pushes are still allowed, and
let CI run once so GitHub has seen the check name. A required status check that
never reports blocks merging forever, and a wrong name is invisible until a pull
request hangs. `-Evaluate` creates the rules in report-only mode first —
violations appear under Settings → Rules → Rule Insights and nothing is blocked.

Do **not** also add a classic branch protection rule. One branch governed by two
mechanisms means every future "why can't I merge this" costs an afternoon.

## `main.json`

Pull requests only, no direct pushes.

* `deletion`, `non_fast_forward` — main cannot be deleted or force-pushed.
* `required_linear_history` plus `allowed_merge_methods: ["squash"]` — one commit
  per change on main, and the merge button cannot produce anything else.
* `pull_request` with **`required_approving_review_count: 0`** — deliberate.
  GitHub does not let anyone approve their own pull request, so a review
  requirement would block every merge while one person maintains this. The
  structure (branch → PR → check → merge) is in place regardless; raise this to
  `1` once a second person is actually working here, and nothing else changes.
* `required_status_checks` with **`tests`** and **`installer`** — the job
  names in [`../workflows/ci.yml`](../workflows/ci.yml). If a job is ever
  renamed without this file changing, pull requests wait forever on a check that
  no longer exists; `tests/test_repo.py` compares the two and fails first.
* `strict_required_status_checks_policy` — a branch must be up to date with main
  before merging, so the checks that passed are the checks that matter.
* `bypass_actors`: repository admins — an emergency route for a broken CI. Using
  it is recorded in Rule Insights.

## `release-tags.json`

`v*` tags cannot be moved, deleted or force-updated, and **nobody** can bypass
it.

A RiftLab release states which RiftRec schema version it reads, and carries the
installer people actually ran. That is what lets a report say "these recordings
were read with RiftLab 0.1.0" and have it mean something. If the tag can be
repointed at a different commit, it stops meaning anything — and the study runs
once.
