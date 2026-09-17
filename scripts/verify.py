#!/usr/bin/env python3
"""Verify this repository from a clean base: install, test, package, convert,
gate, and reproduce the committed examples.

This is the single entry point the Docker image runs. It is also runnable on a
host checkout:

    uv run python -m scripts.verify            # everything
    uv run python -m scripts.verify --offline  # stages needing no network

Design rules this file exists to enforce, each learned the hard way:

* **A stage never skips silently.** Without network, the stages that need it FAIL
  by default and say why. `--offline` converts them to SKIP *and* suppresses any
  overall success claim, because a harness that quietly runs four of eight stages
  and prints a summary is worse than one that fails.
* **The stage count is asserted.** Adding a stage without wiring it into the
  summary fails a test rather than going unnoticed.
* **Provenance is stamped, including dirtiness.** Numbers from a dirty tree are
  not reproducible and are labelled as such.

Stage definitions and expectations:
docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md §9.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The immutable upstream ref the committed examples are pinned to. Changing this
# means examples/ must be regenerated; stage 6 will fail until it is.
PINNED_REF = "Tag_Rel19_SA112"
PINNED_REF_TYPE = "tags"
PINNED_COMMIT = "24ffa42e24c806959fe94cbd3565bc0ffbe4b379"
EXAMPLES_DIR = ROOT / "examples" / "MnS-Rel-19-yang-models"
FORGE_HOST = "https://forge.3gpp.org"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


@dataclass
class StageResult:
    name: str
    status: str
    detail: str = ""
    numbers: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == PASS


class Ctx:
    """Shared state between stages: the working dir and the options."""

    def __init__(self, args):
        self.args = args
        self.workdir = Path(args.output) if args.output else Path(
            tempfile.mkdtemp(prefix="y2r-verify-"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.converted = self.workdir / "converted"
        self.network: bool | None = None


def readme_install_commands(readme: Path) -> list[str]:
    """Shell commands from the README's "## Install" section, in order.

    The Dockerfile must contain each of these verbatim -- that is the anti-drift
    contract, asserted by tests/test_install_docs.py. Comments and blank lines are
    dropped; a trailing `# comment` on a command is trimmed so the comparison is
    against the command itself.

    Returns [] if the section or its fenced block is missing, which is precisely
    why the covering test asserts a COUNT rather than truthiness: a renamed heading
    must fail loudly instead of making every check vacuous.
    """
    text = readme.read_text(encoding="utf-8")
    m = re.search(r"^##\s+Install\s*$(.*?)^##\s+", text, re.M | re.S)
    if not m:
        return []
    block = re.search(r"```bash\n(.*?)```", m.group(1), re.S)
    if not block:
        return []
    cmds = []
    for line in block.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            cmds.append(line)
    return cmds


def _run(cmd: list[str], ctx: Ctx, cwd: Path | None = None) -> tuple[int, str]:
    """Run a command, returning (returncode, combined output).

    Deliberately captures and returns the real exit status separately from the
    output: reading a filtered or piped status is how a failing step gets recorded
    as a pass.
    """
    if ctx.args.dry_run:
        return 0, f"[dry-run] would run: {' '.join(cmd)}"
    p = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _tail(text: str, lines: int = 12) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def have_network(ctx: Ctx) -> bool:
    """Can we reach the 3GPP forge? Cached, and overridable for tests."""
    if ctx.args.simulate_no_network:
        return False
    if ctx.network is not None:
        return ctx.network
    if ctx.args.dry_run:
        ctx.network = True
        return True
    try:
        req = urllib.request.Request(FORGE_HOST, method="HEAD")
        with urllib.request.urlopen(req, timeout=20) as r:
            ctx.network = 200 <= r.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        ctx.network = False
    return ctx.network


def _network_gate(ctx: Ctx, stage: str) -> StageResult | None:
    """Shared refusal for the network-dependent stages.

    Returns a SKIP result only under --offline; otherwise a FAIL. Never None-and-
    carry-on, which is how a stage ends up quietly not running.
    """
    if have_network(ctx):
        return None
    reason = f"no network: cannot reach {FORGE_HOST}"
    if ctx.args.offline:
        return StageResult(stage, SKIP, f"{reason} (--offline requested)")
    return StageResult(stage, FAIL,
                       f"{reason}. Pass --offline to skip stages 4-6 explicitly "
                       f"instead of pretending they ran.")


# --- stages ---------------------------------------------------------------

def stage_provenance(ctx: Ctx) -> StageResult:
    """Record exactly what is being measured, including whether it is dirty."""
    def git(*a) -> str:
        rc, out = _run(["git", *a], ctx)
        return out.strip() if rc == 0 else ""

    # The Docker build excludes .git (image size), so git is unavailable inside
    # the image. The build passes the revision in as Y2R_GIT_HEAD/Y2R_GIT_DIRTY so
    # provenance can still say what it measured. A provenance stage that cannot
    # identify its own revision is close to useless, so this must not be silent:
    # `head` becomes "unknown" and `dirty` None, both visible in the report.
    head = git("rev-parse", "HEAD") or os.environ.get("Y2R_GIT_HEAD", "") or "unknown"
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or \
        os.environ.get("Y2R_GIT_BRANCH", "") or "unknown"
    dirty_rc, dirty_out = _run(["git", "status", "--porcelain"], ctx)
    if dirty_rc == 0:
        dirty = bool(dirty_out.strip())
    elif os.environ.get("Y2R_GIT_DIRTY"):
        dirty = os.environ["Y2R_GIT_DIRTY"] == "1"
    else:
        dirty = None
    numbers = {
        "head": head,
        "branch": branch,
        "dirty": dirty,
        "revision_source": "git" if dirty_rc == 0 else (
            "build-arg" if os.environ.get("Y2R_GIT_HEAD") else "unavailable"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pinned_ref": PINNED_REF,
        "pinned_commit": PINNED_COMMIT,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for mod in ("rdflib", "pyang"):
        try:
            numbers[f"{mod}_version"] = __import__(mod).__version__
        except Exception:
            numbers[f"{mod}_version"] = "unknown"
    detail = f"HEAD {numbers['head'][:12]} (via {numbers['revision_source']})"
    if dirty:
        detail += "  DIRTY TREE -- these numbers are not reproducible"
    elif dirty is None:
        detail += "  cleanliness UNKNOWN -- cannot certify reproducibility"
    return StageResult("provenance", PASS, detail, numbers)


def stage_sync(ctx: Ctx) -> StageResult:
    """The lockfile installs on a clean base."""
    rc, out = _run(["uv", "sync", "--locked"], ctx)
    return StageResult("uv sync --locked", PASS if rc == 0 else FAIL, _tail(out))


def stage_tests(ctx: Ctx) -> StageResult:
    """The unit suite passes.

    Reports the SKIP count as well as the pass count, and says why. Inside the
    image the 3GPP zip is absent (it is not redistributed), so the
    dataset-dependent tests skip -- meaning this stage covers less than the bare
    name "pytest" suggests. Those code paths are covered instead by stages 4-6,
    which fetch the pinned set from the forge and convert it for real. Stating the
    number is the point: a stage whose scope is narrower than its name, left
    unstated, is false assurance.
    """
    rc, out = _run(["uv", "run", "pytest", "-q"], ctx)
    passed = re.search(r"(\d+) passed", out)
    skipped = re.search(r"(\d+) skipped", out)
    n_skip = int(skipped.group(1)) if skipped else 0
    numbers = {"passed": int(passed.group(1)) if passed else None,
               "skipped": n_skip}
    detail = _tail(out, 3)
    if n_skip:
        detail += (f"\n{n_skip} test(s) skipped: the 3GPP zip is not redistributed, "
                   f"so dataset tests skip unless YANG_TEST_ZIP is set. Those paths "
                   f"are exercised by stages 4-6 against the pinned forge tag.")
    return StageResult("pytest", PASS if rc == 0 else FAIL, detail, numbers)


def stage_wheel(ctx: Ctx) -> StageResult:
    """The path a package user takes: build a wheel, install it clean, run it.

    Catches packaging metadata faults that an editable install never shows.
    """
    dist = ctx.workdir / "dist"
    rc, out = _run(["uv", "build", "--out-dir", str(dist)], ctx)
    if rc != 0:
        return StageResult("wheel install", FAIL, _tail(out))
    if ctx.args.dry_run:
        return StageResult("wheel install", PASS, "[dry-run]")
    wheels = sorted(dist.glob("*.whl"))
    if not wheels:
        return StageResult("wheel install", FAIL, f"uv build produced no wheel in {dist}")
    venv = ctx.workdir / "wheelvenv"
    for cmd in (["uv", "venv", str(venv)],
                ["uv", "pip", "install", "--python", str(venv / "bin" / "python"),
                 str(wheels[-1])]):
        rc, out = _run(cmd, ctx)
        if rc != 0:
            return StageResult("wheel install", FAIL, _tail(out))
    rc, out = _run([str(venv / "bin" / "yang-to-rdf"), "--version"], ctx)
    return StageResult("wheel install", PASS if rc == 0 else FAIL, out.strip(),
                       {"wheel": wheels[-1].name})


def stage_convert(ctx: Ctx) -> StageResult:
    """Convert the pinned, immutable input."""
    gate = _network_gate(ctx, "convert pinned input")
    if gate is not None:
        return gate
    rc, out = _run(["uv", "run", "yang-to-rdf",
                    "--fetch-release", PINNED_REF, "--ref-type", PINNED_REF_TYPE,
                    "-o", str(ctx.converted)], ctx)
    if rc != 0:
        return StageResult("convert pinned input", FAIL, _tail(out))
    n = len(list(ctx.converted.glob("*.ttl"))) if not ctx.args.dry_run else 0
    if not ctx.args.dry_run and n == 0:
        return StageResult("convert pinned input", FAIL,
                           "conversion exited 0 but wrote no .ttl files")
    return StageResult("convert pinned input", PASS, _tail(out, 3), {"ttl_files": n})


def stage_gates(ctx: Ctx) -> StageResult:
    """Run the IRI gates over the freshly converted output."""
    gate = _network_gate(ctx, "iri gates")
    if gate is not None:
        return gate
    if ctx.args.dry_run:
        return StageResult("iri gates", PASS, "[dry-run]")
    report = ctx.workdir / "iri-census.json"
    rc, out = _run(["uv", "run", "python", "-m", "scripts.iri_census",
                    str(ctx.converted), "--json", str(report)], ctx)
    numbers = {}
    if report.is_file():
        data = json.loads(report.read_text())
        numbers = dict(data["summary"])
        numbers["gates_passed"] = sum(1 for g in data["gates"] if g["passed"])
        numbers["gates_total"] = len(data["gates"])
    return StageResult("iri gates", PASS if rc == 0 else FAIL, _tail(out), numbers)


def stage_examples(ctx: Ctx) -> StageResult:
    """The committed examples reproduce byte-for-byte. Expectation: zero diffs."""
    gate = _network_gate(ctx, "examples reproduce")
    if gate is not None:
        return gate
    if ctx.args.dry_run:
        return StageResult("examples reproduce", PASS, "[dry-run]")
    if not EXAMPLES_DIR.is_dir():
        return StageResult("examples reproduce", FAIL,
                           f"{EXAMPLES_DIR} is absent (excluded from the image?) "
                           f"-- mount it read-only to run this stage")
    produced = {p.name: p for p in ctx.converted.glob("*.ttl")}
    committed = {p.name: p for p in EXAMPLES_DIR.glob("*.ttl")}
    if not committed:
        return StageResult("examples reproduce", FAIL,
                           f"no .ttl files in {EXAMPLES_DIR} -- nothing to compare")
    only_new = sorted(set(produced) - set(committed))
    only_old = sorted(set(committed) - set(produced))
    differing = sorted(n for n in set(produced) & set(committed)
                       if produced[n].read_bytes() != committed[n].read_bytes())
    numbers = {"produced": len(produced), "committed": len(committed),
               "differing": len(differing), "only_produced": len(only_new),
               "only_committed": len(only_old)}
    problems = differing + only_new + only_old
    detail = (f"{len(produced)} produced vs {len(committed)} committed; "
              f"{len(differing)} differ, {len(only_new)} new, {len(only_old)} missing")
    if problems:
        detail += "\n  " + "\n  ".join(problems[:10])
    return StageResult("examples reproduce", PASS if not problems else FAIL,
                       detail, numbers)


STAGES = [
    ("provenance", stage_provenance),
    ("uv sync --locked", stage_sync),
    ("pytest", stage_tests),
    ("wheel install", stage_wheel),
    ("convert pinned input", stage_convert),
    ("iri gates", stage_gates),
    ("examples reproduce", stage_examples),
]

# An INDEPENDENT literal, deliberately not len(STAGES) + 1.
#
# It was written as `len(STAGES) + 1` first, and inverting the guard -- adding a
# stage to STAGES without touching anything else -- did NOT fail: both sides of
# the assertion derived from STAGES, so it compared a value to itself and could
# never fire. A count assertion whose expected value is computed from the thing it
# checks is a decoration.
#
# Typed by hand, so adding a stage forces a deliberate edit here and the test
# fails until someone has confirmed the new stage is summarised.
# 7 stages + the summary.
STAGE_COUNT = 8

# The `stage_` prefix is reserved for stage implementations, so the
# 'every stage function is wired in' test can enumerate them by name.


def all_stage_names() -> list[str]:
    return [n for n, _ in STAGES] + ["summary"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true",
                    help="permit the network-dependent stages to SKIP when the "
                         "forge is unreachable, instead of failing; the summary "
                         "then reports INCOMPLETE and the exit status is non-zero. "
                         "If the forge IS reachable those stages still run.")
    ap.add_argument("--output", default=None,
                    help="working directory (default: a temp dir)")
    ap.add_argument("--json", default=None, help="write verification-report.json here")
    ap.add_argument("--dry-run", action="store_true",
                    help="exercise the stage wiring without running the work")
    ap.add_argument("--simulate-no-network", action="store_true",
                    help="pretend the forge is unreachable (for testing the gate)")
    a = ap.parse_args(argv)

    ctx = Ctx(a)
    results: list[StageResult] = []
    print(f"yang-to-rdf verification  ({len(STAGES)} stages + summary)")
    print(f"working dir: {ctx.workdir}\n")

    for i, (name, fn) in enumerate(STAGES):
        r = fn(ctx)
        results.append(r)
        print(f"[{i}] {r.status:4s}  {name}")
        if r.detail:
            for line in r.detail.splitlines():
                print(f"        {line}")
        if r.numbers:
            for k, v in r.numbers.items():
                print(f"        {k} = {v}")
        print()
        # A hard failure in install/test invalidates everything after it.
        if r.status == FAIL and name in ("uv sync --locked", "pytest"):
            print("aborting: later stages cannot be trusted after this failure\n")
            break

    # --- summary (the +1 stage) ---
    failed = [r for r in results if r.status == FAIL]
    skipped = [r for r in results if r.status == SKIP]
    ran = len(results)
    print("=" * 64)
    print(f"{'stage':26s} {'status':7s} note")
    for r in results:
        print(f"{r.name:26s} {r.status:7s} {r.detail.splitlines()[0] if r.detail else ''}"[:100])
    if ran < len(STAGES):
        print(f"\n{len(STAGES) - ran} stage(s) never ran (aborted early).")
    print(f"\n{ran - len(failed) - len(skipped)}/{len(STAGES)} passed, "
          f"{len(failed)} failed, {len(skipped)} skipped")

    dirty = results[0].numbers.get("dirty") if results else None
    if dirty:
        print("NOTE: tree was DIRTY -- these numbers are not reproducible.")

    if failed:
        print("RESULT: FAILED")
    elif skipped:
        # Deliberately not a success claim.
        print(f"RESULT: INCOMPLETE -- {len(skipped)} stage(s) skipped, "
              f"so reproducibility is unverified.")
    elif ran < len(STAGES):
        print("RESULT: INCOMPLETE -- aborted early.")
    else:
        print("RESULT: all stages passed")

    report_path = Path(a.json) if a.json else ctx.workdir / "verification-report.json"
    report_path.write_text(json.dumps({
        "stage_count_expected": STAGE_COUNT,
        "stages_defined": all_stage_names(),
        "stages_run": ran,
        "offline": a.offline,
        "results": [asdict(r) for r in results],
    }, indent=2))
    print(f"report: {report_path}")

    return 1 if (failed or skipped or ran < len(STAGES)) else 0


if __name__ == "__main__":
    sys.exit(main())
