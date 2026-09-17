"""Nothing internal, stale, or unimplemented may ship in a public repository.

Every forbidden string below was actually present at some point, so these are
regression guards rather than hypotheticals.

Two tiers, deliberately:

* `FORBIDDEN_EVERYWHERE` — internal hostnames. No file may contain these, design
  records included.
* `FORBIDDEN_IN_LIVE_DOCS` — stale API and IRI references. Historical records are
  exempt from this tier only: the dated design/plan documents, `CHANGELOG.md`, and
  the tests. A changelog documenting "X was removed" must be able to name X, and a
  test asserting X's absence must be able to spell it. The exemption is itself
  asserted to cover only those paths and less than half the repo.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).name

FORBIDDEN_EVERYWHERE = {
    "internal.ericsson.com": "internal hostname",
    "gitlabpages-central": "internal GitLab Pages host",
    "gitlab.internal": "internal GitLab host",
}

FORBIDDEN_IN_LIVE_DOCS = {
    "3gpp.org/nrm/": "IRIs minted under a domain we do not control",
    "--base-namespace": "a flag documented in five places that never existed",
}

# Historical records: they describe the change and so necessarily quote what was
# removed. A changelog documenting "X was removed" must be allowed to name X, and a
# test asserting X's absence must be allowed to spell it.
HISTORICAL = ("docs/superpowers/", "CHANGELOG.md", "tests/")

# Generated Turtle and binaries are not prose; scripts/iri_census.py polices them.
SKIP_SUFFIXES = {".ttl", ".zip", ".docx", ".lock", ".png", ".pdf"}


# Directories that are never part of the shipped repository.
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
             ".mypy_cache", "node_modules", "dist", "output", "public",
             ".superpowers"}


def _scan_source() -> tuple[list[Path], str]:
    """Files to scan, plus which mode produced them.

    Prefers `git ls-files`. Falls back to a filesystem walk when git is
    unavailable -- which is the case inside the Docker image, since .dockerignore
    excludes .git. The fallback exists because these tests previously ERRORED in
    the container with `git ls-files ... exit status 128`, and a hygiene check that
    cannot run in CI is worse than one that fails: it is silent.

    It must never SKIP. `test_the_scan_actually_covers_the_repo` asserts the
    resulting file set is real in either mode.
    """
    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.split():
        return ([ROOT / x for x in r.stdout.split()], "git")
    files = []
    for p in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if p.is_file():
            files.append(p)
    return (files, "walk")


def _tracked() -> list[Path]:
    files, mode = _scan_source()
    assert files, f"the {mode} scan found no files -- this check did not run"
    return [p for p in files if p.is_file() and p.suffix not in SKIP_SUFFIXES]


def _live(paths: list[Path]) -> list[Path]:
    return [p for p in paths
            if not any(p.relative_to(ROOT).as_posix().startswith(h) for h in HISTORICAL)]


def _hits(needle: str, paths: list[Path]) -> list[str]:
    out = []
    for p in paths:
        if p.name == SELF:      # this file necessarily contains its own needles
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if needle in line:
                out.append(f"{p.relative_to(ROOT)}:{i}")
    return out


def test_the_scan_reports_which_mode_it_used():
    """Both modes must yield a real file set; neither may quietly yield nothing."""
    files, mode = _scan_source()
    assert mode in ("git", "walk")
    assert len(files) > 20, f"{mode} scan found only {len(files)} files"


def test_the_scan_actually_covers_the_repo():
    """Without this, an over-broad skip list would make every check vacuous."""
    files = _tracked()
    assert len(files) > 20, f"only {len(files)} files scanned; expected the whole repo"
    names = {p.name for p in files}
    for expected in ("README.md", "CONVERSION_NOTES.md", "VERSIONING.md",
                     "CHANGELOG.md", "Dockerfile", "pyproject.toml"):
        assert expected in names, f"{expected} not among the scanned files"


def test_the_historical_exemption_does_not_swallow_the_live_docs():
    """Guards the exemption's scope: it must cover only dated design records."""
    live = {p.relative_to(ROOT).as_posix() for p in _live(_tracked())}
    # CHANGELOG.md is deliberately exempt (it documents what was removed), so it
    # is NOT listed here. These are the docs a reader follows as instructions.
    for must_be_live in ("README.md", "CONVERSION_NOTES.md", "VERSIONING.md",
                         "examples/MnS-Rel-19-yang-models/README.md",
                         "Dockerfile", "pyproject.toml"):
        assert must_be_live in live, f"{must_be_live} was wrongly exempted"
    exempted = {p.relative_to(ROOT).as_posix() for p in _tracked()} - live
    assert exempted, "the exemption matched nothing -- HISTORICAL is stale"
    assert all(e.startswith(HISTORICAL) for e in exempted), exempted
    # The exemption must stay small: instructional docs are the ones that matter.
    assert len(exempted) < len(_tracked()) / 2, (
        f"{len(exempted)} of {len(_tracked())} files exempted -- too broad to be "
        f"a meaningful check")


@pytest.mark.parametrize("needle,why", sorted(FORBIDDEN_EVERYWHERE.items()))
def test_no_internal_hostname_anywhere(needle, why):
    hits = _hits(needle, _tracked())
    assert not hits, f"{needle!r} ({why}) in {len(hits)} place(s): {hits[:10]}"


@pytest.mark.parametrize("needle,why", sorted(FORBIDDEN_IN_LIVE_DOCS.items()))
def test_no_stale_reference_in_live_docs(needle, why):
    hits = _hits(needle, _live(_tracked()))
    assert not hits, f"{needle!r} ({why}) in {len(hits)} place(s): {hits[:10]}"


def test_gitlab_ci_is_gone():
    """CI moved to GitHub Actions; a stale GitLab config would mislead a reader."""
    assert not (ROOT / ".gitlab-ci.yml").exists()


def test_github_workflow_builds_and_runs_the_container():
    wf = ROOT / ".github" / "workflows" / "ci.yml"
    assert wf.is_file()
    text = wf.read_text()
    assert "docker build" in text, "CI must build the verification image"
    assert "docker run" in text, "CI must actually run the verification"


def test_readme_promises_no_documentation_that_does_not_exist():
    """The internal Pages link was removed rather than replaced: the ontology HTML
    is a known-poor follow-up, and promising it would be worse than silence."""
    text = (ROOT / "README.md").read_text()
    assert "gitlabpages" not in text
    assert not re.search(r"\[Browse the generated ontology documentation\]", text)


def test_minted_vocabulary_prefix_is_consistently_y2r():
    """The nrm: -> y2r: rename must be complete in prose as well as code, or a
    reader copies a prefix that resolves to nothing."""
    offenders = []
    for p in _live(_tracked()):
        if p.name == SELF:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            # `nrm:` used as a PREFIX, not the substring in `_3gpp-5gc-nrm-...`.
            if re.search(r"(?<![\w-])nrm:", line):
                offenders.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()[:70]}")
    assert not offenders, (
        f"{len(offenders)} references to the old nrm: prefix remain:\n"
        + "\n".join(offenders[:15]))


def test_the_prefix_scan_can_actually_fire(tmp_path):
    """Inverted: the regex must match a real `nrm:` use and must NOT match the
    substring inside a module name, or the check above proves nothing."""
    assert re.search(r"(?<![\w-])nrm:", "load the `nrm:` vocabulary")
    assert re.search(r"(?<![\w-])nrm:", "nrm:hasAttribute")
    assert not re.search(r"(?<![\w-])nrm:", "_3gpp-5gc-nrm-amffunction")
    assert not re.search(r"(?<![\w-])nrm:", "urn:3gpp:sa5:_3gpp-nr-nrm-bwp")
