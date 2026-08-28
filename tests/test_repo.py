"""The repository's own wiring: CI, branch rules, release.

These are not tests of RiftLab's behaviour. They pin the agreements that have no
other guardrail - above all the one GitHub gives no warning for: a required
status check whose job was renamed. The pull request then simply never becomes
mergeable, and nothing anywhere says why.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
RELEASE = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
RULESET_DIR = ROOT / ".github" / "rulesets"


def _ruleset(name: str) -> dict:
    return json.loads((RULESET_DIR / name).read_text(encoding="utf-8"))


def _rule(ruleset: dict, kind: str) -> dict:
    """The one rule of a given type, so a missing rule fails loudly."""
    matches = [r for r in ruleset["rules"] if r["type"] == kind]
    assert len(matches) == 1, (kind, ruleset["name"])
    return matches[0]


def _jobs(workflow: str) -> set[str]:
    return set(re.findall(r"^  ([a-zA-Z][\w-]*):$",
                          workflow.split("jobs:", 1)[1], re.MULTILINE))


def test_required_checks_match_the_ci_job_names() -> None:
    """The drift that blocks every pull request forever, silently."""
    checks = _rule(_ruleset("main.json"), "required_status_checks")
    required = [c["context"] for c in checks["parameters"]["required_status_checks"]]
    assert required, required
    for check in required:
        assert check in _jobs(CI), (check, sorted(_jobs(CI)))


def test_ci_runs_on_every_pull_request_without_a_path_filter() -> None:
    """A required check that is skipped because no path matched leaves the pull
    request waiting for a report that never comes."""
    trigger = CI.split("jobs:", 1)[0]
    assert "pull_request:" in trigger
    assert "paths:" not in trigger


def test_main_takes_no_direct_pushes() -> None:
    main = _ruleset("main.json")
    assert main["target"] == "branch"
    assert main["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
    for kind in ("deletion", "non_fast_forward", "required_linear_history",
                 "pull_request", "required_status_checks"):
        _rule(main, kind)


def test_no_review_requirement_while_the_project_is_one_person() -> None:
    """GitHub does not allow approving your own pull request, so a review
    requirement would block every merge for a solo maintainer. Raise it to 1
    once a second person is actually working here."""
    params = _rule(_ruleset("main.json"), "pull_request")["parameters"]
    assert params["required_approving_review_count"] == 0


def test_release_tags_cannot_be_moved_or_deleted() -> None:
    """A release names the RiftRec schema version it reads. If the tag can be
    repointed, that statement stops meaning anything."""
    tags = _ruleset("release-tags.json")
    assert tags["target"] == "tag"
    assert tags["conditions"]["ref_name"]["include"] == ["refs/tags/v*"]
    for kind in ("deletion", "update", "non_fast_forward"):
        _rule(tags, kind)
    assert tags["bypass_actors"] == []


def test_release_refuses_a_tag_that_disagrees_with_the_package_version() -> None:
    assert "__version__" in RELEASE
    assert "does not match" in RELEASE
    assert "origin/main" in RELEASE


def test_both_workflows_run_the_test_suite() -> None:
    for workflow in (CI, RELEASE):
        assert "pytest tests/" in workflow


def test_the_interpreter_is_pinned_to_one_patch_version_in_one_place() -> None:
    """"3.12" floats: the same tag rebuilt months later runs on a different
    interpreter and produces a different binary. The version lives in
    .python-version so there is one thing to raise, not three."""
    pin = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", pin), pin

    for workflow in (CI, RELEASE):
        assert "python-version-file: .python-version" in workflow
        # no workflow may carry its own copy of the number
        assert not re.search(r'python-version:\s*"', workflow), workflow[:80]

    build = (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8")
    assert ".python-version" in build, "the local build does not know the pin"


def test_the_two_workflows_agree_on_action_versions() -> None:
    """One bumped and the other forgotten is how a release starts failing on a
    runner change, months after CI stopped warning about it."""
    def used(workflow: str) -> dict:
        return dict(re.findall(r"uses:\s*([\w.-]+/[\w.-]+)@(v[\w.]+)", workflow))

    ci, release = used(CI), used(RELEASE)
    shared = set(ci) & set(release)
    assert shared, "the two workflows share no actions at all - one is misparsed"
    for action in sorted(shared):
        assert ci[action] == release[action], (action, ci[action], release[action])


def test_every_ruleset_is_valid_json_and_enforced() -> None:
    for path in RULESET_DIR.glob("*.json"):
        ruleset = _ruleset(path.name)
        assert ruleset["name"]
        assert ruleset["target"] in ("branch", "tag"), path
        assert ruleset["enforcement"] == "active", path


def test_every_job_that_builds_the_installer_installs_pyinstaller() -> None:
    """What broke the v0.1.0 release: the release job ran the build-installer
    action without having installed the tool the action shells out to. The tests
    passed first, so the failure came late and cost a version number - a tag
    cannot be moved once it exists, which is the point of protecting it.

    Checking "both workflows use the action" was not enough; this checks that
    both can actually run it.
    """
    for name, workflow in (("ci.yml", CI), ("release.yml", RELEASE)):
        if "./.github/actions/build-installer" not in workflow:
            continue
        # The actual install commands, not the whole file - a comment
        # mentioning pyinstaller must not satisfy this.
        installs = [line for line in workflow.splitlines() if "pip install" in line]
        assert any("pyinstaller" in line for line in installs), (
            f"{name} runs the build-installer action but never installs "
            f"pyinstaller; its pip lines are {installs}")
