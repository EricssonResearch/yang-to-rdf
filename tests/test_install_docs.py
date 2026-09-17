"""The Dockerfile IS the install documentation; they must not drift.

The failure this exists to prevent: README install instructions that quietly stop
working because nothing executes them. The Dockerfile does execute them, in CI, so
the only remaining risk is the two diverging -- which is what these tests pin.
"""
from pathlib import Path

import pytest

from scripts.verify import readme_install_commands

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
DOCKERFILE = ROOT / "Dockerfile"

# Commands the container legitimately replaces: getting the source into place.
# `git clone` becomes `COPY . .` and `cd` becomes `WORKDIR`. Both are declared
# here rather than the check being loosened -- an undeclared divergence must fail.
SUBSTITUTED = ("git clone", "cd yang-to-rdf")


def test_readme_install_section_exists_and_yields_commands():
    """A count assertion, not just a truthiness one: if the heading is renamed the
    extractor would return [] and every other test here would vacuously pass."""
    cmds = readme_install_commands(README)
    assert len(cmds) == 3, (
        f"extracted {len(cmds)} commands from README Install: {cmds}. Expected "
        f"exactly the clone, the cd and the locked sync -- if this count changes, "
        f"decide deliberately whether the new command is substituted or verbatim.")


def test_every_non_substituted_command_is_in_the_dockerfile_verbatim():
    cmds = readme_install_commands(README)
    verbatim = [c for c in cmds if not any(s in c for s in SUBSTITUTED)]
    assert verbatim, (
        f"0 of {len(cmds)} commands are checked verbatim -- SUBSTITUTED has "
        f"swallowed them all, so this test proves nothing")
    dockerfile = DOCKERFILE.read_text()
    missing = [c for c in verbatim if c not in dockerfile]
    assert not missing, (
        f"{len(missing)} of {len(verbatim)} verbatim README install commands are "
        f"absent from the Dockerfile: {missing}")


def test_every_substituted_command_is_declared_in_the_dockerfile():
    """Each difference must be documented where a reader stands -- in the
    Dockerfile itself -- and each must actually be substituted by something."""
    dockerfile = DOCKERFILE.read_text()
    for s in SUBSTITUTED:
        assert s in dockerfile, (
            f"the Dockerfile must name {s!r} in a comment as a command it replaces")
    assert "COPY . ." in dockerfile, "git clone must be replaced by a COPY"
    assert "WORKDIR /yang-to-rdf" in dockerfile, "cd must be replaced by a WORKDIR"


def test_substituted_commands_are_all_actually_in_the_readme():
    """Guards the other direction: a stale SUBSTITUTED entry would silently
    exempt a command that no longer exists, weakening the verbatim check."""
    cmds = readme_install_commands(README)
    for s in SUBSTITUTED:
        assert any(s in c for c in cmds), (
            f"{s!r} is exempted but no longer appears in the README: {cmds}")


def test_the_locked_sync_is_what_is_documented():
    """`uv sync` and `uv sync --locked` are different promises: only the latter
    proves the committed lockfile is what gets installed."""
    cmds = readme_install_commands(README)
    assert any("uv sync --locked" in c for c in cmds), cmds
    assert "uv sync --locked" in DOCKERFILE.read_text()


def test_readme_documents_how_to_run_the_verification():
    text = README.read_text()
    assert "docker build -t yang-to-rdf ." in text
    assert "docker run" in text
    # The offline behaviour is a promise about correctness; it must be stated.
    assert "--offline" in text


def test_dockerignore_excludes_examples_and_says_why():
    """examples/ is excluded for image size, which makes the reproducibility stage
    need a mount. That trade-off must be explained where it is made."""
    di = (ROOT / ".dockerignore").read_text()
    assert "examples" in di
    assert "mount" in di.lower(), ".dockerignore must explain the consequence"


@pytest.mark.parametrize("path", [README, DOCKERFILE, ROOT / ".dockerignore"])
def test_files_exist(path):
    assert path.is_file(), path
