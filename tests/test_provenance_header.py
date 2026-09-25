"""Every generated artifact must carry its provenance, and NOTICE must disclaim them.

Adapted from the sibling `openapi-to-rdf` project's
`tests/test_generated_file_provenance.py`. The point of these tests is that a header
is the kind of thing that silently stops being emitted when a new output path is
added -- so the guard enumerates the files and counts them.

The third test is the load-bearing one: the header is Turtle *comments*, so it must
not change the parsed graph. If it ever did, every downstream consumer would be
reading different triples than before for a cosmetic reason.
"""
import subprocess
from pathlib import Path

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic

from yang_to_rdf.provenance import (
    CONTACT,
    LAYER_TITLES,
    PROJECT_URL,
    provenance_header,
    regenerate_command,
    source_label,
)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "MnS-Rel-19-yang-models"

# Phrases the disclaimer must contain. Deliberately few and load-bearing: these are
# the sentences that stop a reader citing the output as a standards body's own model.
# Not a style check -- each asserts a statement that carries legal weight.
REQUIRED_IN_HEADER = (
    "GENERATED FILE",
    "produced by yang-to-rdf",
    PROJECT_URL,
    CONTACT,
    # The attribution split, which is the substance of the disclaimer. Added after
    # an inversion: deleting this sentence from the header changed nothing, because
    # the list only covered the two sentences after it. The guard's coverage was
    # narrower than the statement it was guarding.
    "The CONVERSION is this project's work",
    "are the source YANG's own wording",
    "did not produce, review or endorse",
    "must not be cited as their model",
    "See NOTICE",
    "Regenerate:",
)


def _header_prose(path: Path) -> str:
    """The comment block as continuous prose, with `# ` prefixes and line wrapping
    removed.

    Matching the raw text fails on wrapping: "did not produce, review or endorse"
    is split across two lines in the real header. Asserting the STATEMENT rather
    than its line breaks means rewrapping the prose does not break the guard, while
    deleting the disclaimer still does.
    """
    lines = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.startswith("#"):
            break
        lines.append(ln.lstrip("#").strip())
    return " ".join(lines)


def _committed_ttl() -> list[Path]:
    files = sorted(EXAMPLES.glob("*.ttl"))
    assert files, f"no .ttl in {EXAMPLES} -- this check did not run"
    return files


def test_every_generated_ttl_carries_a_provenance_header():
    """Counted, so a file that loses its header fails loudly rather than blending in."""
    files = _committed_ttl()
    missing = []
    for f in files:
        prose = _header_prose(f)
        assert prose, f"{f.name}: no comment block at all"
        absent = [p for p in REQUIRED_IN_HEADER if p not in prose]
        if absent:
            missing.append(f"{f.name}: missing {absent}")
    assert not missing, (
        f"{len(missing)} of {len(files)} generated files lack a complete header:\n"
        + "\n".join(missing[:10]))


def test_the_header_names_the_module_it_came_from():
    """A header that does not say what it was converted from is decoration."""
    files = [f for f in _committed_ttl() if f.name != "index.ttl"]
    assert files
    wrong = []
    for f in files:
        stem = f.stem
        for suffix in ("_rdf", "_shacl", "_refs"):
            stem = stem.removesuffix(suffix)
        if f"Source: {stem} " not in _header_prose(f):
            wrong.append(f.name)
    assert not wrong, f"{len(wrong)} of {len(files)} do not name their module: {wrong[:8]}"


def test_the_header_names_the_immutable_upstream_ref():
    """The committed snapshot is pinned; the header must say to what, or the
    'Regenerate' line cannot actually reproduce the file."""
    prose = _header_prose(EXAMPLES / "index.ttl")
    assert "Tag_Rel19_SA112" in prose
    assert "--ref-type tags" in prose


def test_the_header_does_not_change_the_graph():
    """The whole file must parse to the same graph as the file with the comment
    block stripped. Comments are not triples, and this is what proves it."""
    checked = 0
    for f in _committed_ttl()[:12]:      # a sample: the property is per-file uniform
        text = f.read_text(encoding="utf-8")
        body = "".join(ln for ln in text.splitlines(keepends=True)
                       if not ln.startswith("#"))
        assert len(body) < len(text), f"{f.name}: nothing was stripped -- no header?"
        with_header, without = Graph(), Graph()
        with_header.parse(data=text, format="turtle")
        without.parse(data=body, format="turtle")
        assert isomorphic(with_header, without), f"{f.name}: the header changed the graph"
        assert len(with_header) > 0, f"{f.name}: parsed to an empty graph"
        checked += 1
    assert checked == 12, f"only {checked} files compared"


def test_the_header_leaks_no_local_path():
    """A path from the generating machine is not reproducible and would also break
    the container's byte-for-byte stage, which converts into a temp directory.
    Caught exactly that way: the first version interpolated the real output dir."""
    offenders = []
    for f in _committed_ttl():
        prose = _header_prose(f)
        for marker in ("/tmp/", "/home/", "C:\\", "y2r-verify"):
            if marker in prose:
                offenders.append(f"{f.name}: {marker}")
    assert not offenders, offenders


def test_the_regenerate_command_is_output_directory_independent():
    """Two runs into different directories must produce identical headers."""
    a = regenerate_command("Tag_Rel19_SA112", "tags")
    b = regenerate_command("Tag_Rel19_SA112", "tags")
    assert a == b
    assert "<output-dir>" in a
    assert "/tmp" not in a


@pytest.mark.parametrize("layer", sorted(LAYER_TITLES))
def test_each_layer_gets_its_own_title(layer):
    h = provenance_header(layer, "src", "cmd")
    assert LAYER_TITLES[layer] in h


def test_source_label_never_includes_a_supplied_path():
    """When a local set is used the header says so WITHOUT the path."""
    assert source_label(None, None) == "a locally supplied YANG module set"
    assert "/" not in source_label(None, None, module=None)
    assert source_label("Tag_X", "tags", "mod-a").startswith("mod-a (from 3GPP")


# --- NOTICE ---------------------------------------------------------------

def test_notice_exists_and_disclaims_the_generated_artifacts():
    n = (ROOT / "NOTICE").read_text(encoding="utf-8")
    for required in ("not 3GPP's work",
                     "may be cited as their own model",
                     "Not present in this repository",
                     "Tag_Rel19_SA112"):
        assert required in n, f"NOTICE is missing: {required!r}"


def test_notice_records_the_unverified_question():
    """The one item a reviewer may have to rule on must not be left implicit."""
    n = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "## Unverified" in n
    assert "has **not** been verified" in n


def test_notice_claim_that_no_yang_is_tracked_is_true():
    """NOTICE asserts the source is not redistributed. Verify it against git rather
    than trusting the sentence -- a claim in a NOTICE is exactly the kind that must
    be checked against the repository it describes."""
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True)
    if out.returncode != 0:
        pytest.skip("git unavailable (e.g. inside the container, which excludes .git)")
    tracked = out.stdout.split()
    assert tracked, "git ls-files returned nothing -- this check did not run"
    offenders = [f for f in tracked if f.endswith((".yang", ".zip"))]
    assert not offenders, f"NOTICE says no YANG is redistributed, but: {offenders}"


def test_readme_points_at_the_notice():
    assert "NOTICE" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_provenance_module_is_the_only_definition_of_the_contact():
    """Two copies of a contact address drift the moment one is updated."""
    hits = []
    for p in sorted((ROOT / "yang_to_rdf").glob("*.py")) + \
            sorted((ROOT / "scripts").glob("*.py")):
        if p.name == "provenance.py":
            continue
        if CONTACT in p.read_text(encoding="utf-8"):
            hits.append(p.name)
    assert not hits, f"the contact address is duplicated in: {hits}"


def test_the_header_check_can_fail(tmp_path):
    """Inverted: a file without a header must be detected. Without this, the
    enumeration above could be scanning nothing and still pass."""
    bare = tmp_path / "bare.ttl"
    bare.write_text("@prefix ex: <https://ex/> .\nex:A a ex:B .\n")
    assert _header_prose(bare) == "", "a header-less file must yield no prose"
    absent = [p for p in REQUIRED_IN_HEADER if p not in _header_prose(bare)]
    assert len(absent) == len(REQUIRED_IN_HEADER), \
        "a header-less file should be missing every required phrase"
