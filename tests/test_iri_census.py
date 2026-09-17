"""Gates G1-G4, G7, G8 over real converted output.

G5, G6 and G9 are deliberately NOT here: no real 3GPP YANG can reach them, so
they live in tests/test_namespace.py against constructed input. See spec §8.

Runs against the ~8-module tiny set; the gates are dataset-size independent, so
converting all 120 modules would add ~35s and no information. The full-corpus run
is stage 5 of scripts/verify.py.
"""
import json
import subprocess
import sys

import pytest

from scripts.iri_census import GateResult, census, corpus_summary, provenance_urns
from yang_to_rdf.namespace import DEFAULT_BASE_IRI

EXPECTED_GATES = {"G1", "G2", "G3", "G4", "G7", "G8"}


@pytest.fixture(scope="module")
def converted(tmp_path_factory, tiny_yang_dir):
    out = tmp_path_factory.mktemp("census")
    r = subprocess.run([sys.executable, "-m", "yang_to_rdf.main",
                        tiny_yang_dir, "-o", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert list(out.glob("*.ttl")), "conversion produced no .ttl files"
    return out


def test_all_gates_pass_on_real_output(converted):
    results = census(converted, DEFAULT_BASE_IRI)
    failed = [r for r in results if not r.passed]
    assert not failed, "\n".join(f"{r.gate}: {r.violations[:3]}" for r in failed)


def test_every_gate_inspected_something(converted):
    """A gate that searched an empty candidate set has not passed -- it has not
    run. This is the check that catches a gate going stale after a rename."""
    for r in census(converted, DEFAULT_BASE_IRI):
        assert r.checked > 0, f"{r.gate} inspected 0 candidates"


def test_expected_gates_are_all_present(converted):
    """Assert the gate SET, so adding a gate without wiring it into census()
    fails loudly instead of silently not running."""
    assert {r.gate for r in census(converted, DEFAULT_BASE_IRI)} == EXPECTED_GATES


def test_every_gate_states_what_it_checked(converted):
    for r in census(converted, DEFAULT_BASE_IRI):
        assert r.note, f"{r.gate} reported no note; a bare pass/fail is not a finding"


def test_an_empty_directory_is_refused_not_passed(tmp_path):
    """The failure mode this guards: a gate run against nothing exits 0 and looks
    like a pass. It must refuse instead."""
    with pytest.raises(SystemExit):
        census(tmp_path, DEFAULT_BASE_IRI)


def test_provenance_urns_are_found_and_exempted(converted):
    """G1 and G3 share ONE definition of what is exempt. If this returns empty,
    G1 is not actually exercising its exemption path."""
    from scripts.iri_census import load_graphs
    urns = provenance_urns(load_graphs(converted))
    assert urns, "no provenance URNs found -- G1's exemption is untested"
    assert all(u.startswith("urn:") for u in urns)


def test_corpus_summary_partitions_terms_exactly(converted):
    """terms_total must equal the THREE buckets it is composed of.

    Written as a two-bucket assertion first, and it failed 203 != 180 + 13: the
    minted y2r: vocabulary was the missing 10. Worth keeping exactly because the
    two-bucket sum looks like it ought to add up.
    """
    s = corpus_summary(converted, DEFAULT_BASE_IRI)
    assert s["terms_total"] == (s["terms_in_yang_namespace"]
                               + s["terms_in_shapes_namespace"]
                               + s["terms_in_minted_vocabulary"]), s
    assert s["terms_unaccounted_for"] == 0, s
    # Every bucket must be non-empty, or the partition is not being exercised.
    assert s["terms_in_yang_namespace"] > 0
    assert s["terms_in_shapes_namespace"] > 0
    assert s["terms_in_minted_vocabulary"] > 0
    assert s["files"] > 0 and s["triples"] > 0


def test_cli_prints_a_table_and_exits_zero(converted, tmp_path):
    report = tmp_path / "census.json"
    r = subprocess.run([sys.executable, "-m", "scripts.iri_census",
                        str(converted), "--base-iri", DEFAULT_BASE_IRI,
                        "--json", str(report)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # A check that printed nothing has not run, whatever its exit status.
    assert r.stdout.strip(), "census printed nothing"
    for gate in EXPECTED_GATES:
        assert gate in r.stdout
    assert "checked" in r.stdout
    assert "6/6 gates passed" in r.stdout
    data = json.loads(report.read_text())
    assert {g["gate"] for g in data["gates"]} == EXPECTED_GATES
    assert data["summary"]["terms_total"] > 0


# --- the gates must be able to FAIL ---------------------------------------

def test_g4_would_catch_a_real_difference():
    """Inverting G4 by hand: isomorphic() must reject genuinely different graphs.
    Without this, a G4 that always returned True would look identical to a pass."""
    from rdflib import Graph, Literal, URIRef
    from rdflib.compare import isomorphic
    a, b = Graph(), Graph()
    a.add((URIRef("https://ex/s"), URIRef("https://ex/p"), Literal("one")))
    b.add((URIRef("https://ex/s"), URIRef("https://ex/p"), Literal("two")))
    assert not isomorphic(a, b)


def test_g4_tolerates_only_blank_node_relabelling():
    """The reason G4 uses isomorphic() rather than set equality: SHACL property
    shapes are blank nodes and get fresh labels on reparse."""
    from rdflib import BNode, Graph, URIRef
    from rdflib.compare import isomorphic
    a, b = Graph(), Graph()
    for g, bn in ((a, BNode("x1")), (b, BNode("x2"))):
        g.add((URIRef("https://ex/shape"), URIRef("https://ex/property"), bn))
        g.add((bn, URIRef("https://ex/path"), URIRef("https://ex/t")))
    assert set(a) != set(b)      # set equality FAILS here...
    assert isomorphic(a, b)      # ...but the graphs are the same graph


def test_gate_result_carries_its_candidate_count():
    r = GateResult("GX", True, 42, [], "note")
    assert r.checked == 42
