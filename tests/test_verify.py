"""The verification harness itself.

Two properties matter more than any individual stage: that a new stage cannot
appear unsummarised, and that missing network FAILS rather than skipping quietly.
Both are asserted here. See spec §9.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts import verify
from scripts.verify import FAIL, PASS, SKIP, STAGE_COUNT, all_stage_names

ROOT = Path(__file__).resolve().parent.parent


def _run(*args, ):
    return subprocess.run([sys.executable, "-m", "scripts.verify", *args],
                          capture_output=True, text=True, cwd=ROOT)


def test_stage_count_matches_the_stages_defined():
    """Adding a stage without updating STAGE_COUNT fails here, so a stage cannot
    appear without being counted in the summary."""
    names = all_stage_names()
    assert len(names) == STAGE_COUNT, (
        f"{len(names)} stages defined ({names}) but STAGE_COUNT is {STAGE_COUNT}")


def test_stage_names_are_unique_and_include_the_summary():
    names = all_stage_names()
    assert len(set(names)) == len(names), f"duplicate stage name in {names}"
    assert names[-1] == "summary", "the summary must be counted as a stage"
    assert names[0] == "provenance", "provenance must come first"


def test_every_stage_function_is_wired_in():
    """Guards the scope of the count: a stage_* function that exists but is not in
    STAGES would make STAGE_COUNT honest and the harness still incomplete."""
    defined = {n for n in dir(verify) if n.startswith("stage_")}
    wired = {fn.__name__ for _, fn in verify.STAGES}
    assert defined == wired, f"defined but not wired: {sorted(defined - wired)}"


def test_dry_run_exercises_every_stage_and_exits_zero():
    r = _run("--dry-run")
    assert r.stdout.strip(), "verification printed nothing"
    for name, _ in verify.STAGES:
        assert name in r.stdout, f"stage {name!r} missing from output"
    assert "RESULT: all stages passed" in r.stdout
    assert r.returncode == 0, r.stdout[-2000:]


def test_missing_network_fails_by_default_rather_than_skipping():
    """The central promise: a harness that quietly runs half its stages and prints
    a summary is worse than one that fails."""
    r = _run("--dry-run", "--simulate-no-network")
    assert r.returncode != 0, "missing network must fail without --offline"
    assert FAIL in r.stdout
    assert "no network" in r.stdout
    assert "RESULT: FAILED" in r.stdout
    assert "all stages passed" not in r.stdout


def test_offline_skips_with_a_reason_and_refuses_to_claim_success():
    r = _run("--dry-run", "--simulate-no-network", "--offline")
    assert SKIP in r.stdout
    assert "no network" in r.stdout, "a skip must state its reason"
    assert "--offline requested" in r.stdout
    assert "INCOMPLETE" in r.stdout
    assert "all stages passed" not in r.stdout
    # Exit non-zero: an incomplete verification is not a passing one.
    assert r.returncode != 0


def test_network_dependent_stages_are_exactly_the_ones_gated():
    """Pins WHICH stages need network, so silently adding a network call to an
    offline stage shows up here."""
    r = _run("--dry-run", "--simulate-no-network", "--offline")
    skipped = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("[")
               and SKIP in ln]
    assert len(skipped) == 3, f"expected 3 network stages skipped, got: {skipped}"
    for expected in ("convert pinned input", "iri gates", "examples reproduce"):
        assert any(expected in ln for ln in skipped), expected


def test_report_is_written_and_records_provenance(tmp_path):
    report = tmp_path / "verification-report.json"
    r = _run("--dry-run", "--json", str(report), "--output", str(tmp_path / "wd"))
    assert r.returncode == 0, r.stdout[-2000:]
    data = json.loads(report.read_text())
    assert data["stage_count_expected"] == STAGE_COUNT
    assert data["stages_defined"] == all_stage_names()
    assert data["stages_run"] == len(verify.STAGES)
    prov = data["results"][0]
    assert prov["name"] == "provenance"
    assert prov["status"] == PASS
    # Reproducibility depends on knowing the revision AND its cleanliness.
    for key in ("head", "dirty", "pinned_ref", "pinned_commit", "timestamp"):
        assert key in prov["numbers"], key


def test_pinned_ref_is_a_tag_not_a_branch():
    """A branch tip moves, which is what made the previous examples snapshot
    irreproducible. The pin must be immutable."""
    assert verify.PINNED_REF_TYPE == "tags"
    assert verify.PINNED_REF.startswith("Tag_")
    assert len(verify.PINNED_COMMIT) == 40


def test_examples_dir_points_at_the_committed_snapshot():
    """Pins the PATH, deliberately not its existence: examples/ is excluded from
    the Docker build context, so an is_dir() assertion here failed inside the
    container for an environment reason rather than a defect. Whether the
    directory is actually present is stage 6's business, and it FAILS with an
    explanatory message when it is not."""
    assert verify.EXAMPLES_DIR.name == "MnS-Rel-19-yang-models"
    assert verify.EXAMPLES_DIR.parent.name == "examples"
    assert verify.EXAMPLES_DIR.parent.parent == verify.ROOT


# --- readme_install_commands, the anti-drift extractor --------------------

def test_readme_install_commands_returns_empty_for_a_missing_section(tmp_path):
    """The extractor's failure mode, made explicit: no section means no commands,
    which is why its covering test asserts a count."""
    p = tmp_path / "R.md"
    p.write_text("# Title\n\nno install section here\n")
    assert verify.readme_install_commands(p) == []


def test_readme_install_commands_strips_comments_and_blanks(tmp_path):
    p = tmp_path / "R.md"
    p.write_text("## Install\n\n```bash\nfoo --bar   # a note\n\nbaz\n```\n\n## Next\n")
    assert verify.readme_install_commands(p) == ["foo --bar", "baz"]


def test_package_version_matches_the_cli_version():
    """The Docker wheel stage caught these disagreeing: main.py said 0.3.0 while
    pyproject.toml still said 0.2.0. Derive both from one place would be better
    still, but at minimum they must not silently diverge."""
    import re as _re
    pyproject = (ROOT / "pyproject.toml").read_text()
    main_py = (ROOT / "yang_to_rdf" / "main.py").read_text()
    pkg = _re.search(r'^version = "([^"]+)"', pyproject, _re.M)
    cli = _re.search(r'version="%\(prog\)s ([^"]+)"', main_py)
    assert pkg and cli, "could not locate both version strings -- check did not run"
    assert pkg.group(1) == cli.group(1), (
        f"pyproject.toml says {pkg.group(1)}, main.py --version says {cli.group(1)}")


def test_pytest_stage_reports_its_skip_count():
    """A stage whose scope is narrower than its name must say so. Inside the image
    the dataset tests skip, and that number has to be visible or the stage gives
    false assurance."""
    import inspect
    src = inspect.getsource(verify.stage_tests)
    assert "skipped" in src
    assert "YANG_TEST_ZIP" in src, "the stage must name how to widen its scope"
