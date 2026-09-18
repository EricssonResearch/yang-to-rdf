"""Does the emitted SHACL actually validate? Checked with a real SHACL engine.

Why this file exists. Everything in `tests/test_shacl_converter.py` asserts that
triples in the `sh:` namespace are present and correctly shaped. That is a check on
the *vocabulary* we emit, not on whether a SHACL processor accepts it or enforces
anything. The README claims "SHACL **validation** shapes", and until this file was
written no processor had ever loaded the output — so the load-bearing half of that
claim was unverified.

Two distinct properties are checked here, and they are not the same:

1. **Shape validity** — a SHACL processor compiles every emitted shapes file.
2. **Enforcement** — each constraint kind is observed *rejecting* invalid data AND
   *accepting* valid data.

(2) matters because an empty data graph conforms to any shapes graph. A test that
only ever validated conforming (or absent) data would pass no matter how broken the
shapes were: a null from an instrument that can only produce nulls. So every
constraint kind below is exercised in both directions.
"""
import glob
from pathlib import Path

import pyshacl
import pytest
import rdflib
from rdflib import Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF

SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "MnS-Rel-19-yang-models"

# Constraint kinds the converter emits. Asserted as a set, so a kind that stops
# being emitted (or a new one appearing untested) fails rather than going unnoticed.
EXPECTED_CONSTRAINT_KINDS = {"in", "pattern", "minCount", "maxCount", "datatype", "class"}


def _shape_files() -> list[str]:
    files = sorted(glob.glob(str(EXAMPLES / "*_shacl.ttl")))
    assert files, f"no *_shacl.ttl in {EXAMPLES} -- this check did not run"
    return files


@pytest.fixture(scope="module")
def merged_shapes() -> Graph:
    g = Graph()
    for f in _shape_files():
        g.parse(f, format="turtle")
    assert len(g) > 1000, f"merged shapes graph is only {len(g)} triples"
    return g


def _validate(data: Graph, shapes: Graph):
    """Returns (conforms, set of constraint-component names that fired)."""
    conforms, results, _ = pyshacl.validate(
        data, shacl_graph=shapes, inference="none",
        allow_infos=True, allow_warnings=True)
    fired = {
        str(next(results.objects(r, SH.sourceConstraintComponent), "")).rsplit("#")[-1]
        for r in results.subjects(SH.resultSeverity, None)
    }
    return conforms, fired - {""}


# --- 1. shape validity ----------------------------------------------------

@pytest.mark.slow
def test_a_shacl_processor_compiles_every_shape_file():
    """118 files, 1182 NodeShapes at the time of writing. A file a processor
    refuses is a real defect: the output would not be usable as SHACL at all."""
    refused, n_shapes = [], 0
    for f in _shape_files():
        sg = Graph()
        sg.parse(f, format="turtle")
        n_shapes += len(list(sg.subjects(RDF.type, SH.NodeShape)))
        try:
            # Compiling is the check. The empty data graph conforms trivially --
            # enforcement is tested separately below.
            pyshacl.validate(Graph(), shacl_graph=sg, inference="none")
        except Exception as e:  # noqa: BLE001 -- any refusal is the finding
            refused.append(f"{Path(f).name}: {type(e).__name__}: {e}")
    assert n_shapes > 0, "compiled 0 NodeShapes -- the check did not run"
    assert not refused, f"{len(refused)} of {len(_shape_files())} refused: {refused[:3]}"


def test_every_expected_constraint_kind_is_emitted(merged_shapes):
    """Pins WHICH constraint kinds exist, so this file's coverage cannot silently
    become narrower than the output."""
    present = {k for k in EXPECTED_CONSTRAINT_KINDS
               if list(merged_shapes.triples((None, SH[k], None)))}
    assert present == EXPECTED_CONSTRAINT_KINDS, (
        f"missing: {sorted(EXPECTED_CONSTRAINT_KINDS - present)}")


# --- 2. enforcement, both directions --------------------------------------
# A single small module keeps these fast; the constraint kinds are what is under
# test, not the size of the corpus.

@pytest.fixture(scope="module")
def eutranetwork():
    """A minimal real shape: EUtraNetwork.id, xsd:string, sh:maxCount 1."""
    g = Graph()
    g.parse(EXAMPLES / "_3gpp-nr-nrm-eutranetwork_shacl.ttl", format="turtle")
    ns = rdflib.Namespace(
        "https://semantics.ericsson.com/yang/_3gpp-nr-nrm-eutranetwork#")
    return g, ns.EUtraNetwork, ns["EUtraNetwork.id"]


def test_conforming_instance_conforms(eutranetwork):
    shapes, cls, path = eutranetwork
    d = Graph()
    d.add((URIRef("urn:ex:n"), RDF.type, cls))
    d.add((URIRef("urn:ex:n"), path, Literal("net-1")))
    conforms, fired = _validate(d, shapes)
    assert conforms, f"valid data rejected by {fired}"


def test_max_count_is_enforced(eutranetwork):
    """YANG cardinality became a constraint that actually rejects."""
    shapes, cls, path = eutranetwork
    d = Graph()
    d.add((URIRef("urn:ex:n"), RDF.type, cls))
    d.add((URIRef("urn:ex:n"), path, Literal("a")))
    d.add((URIRef("urn:ex:n"), path, Literal("b")))   # maxCount 1 violated
    conforms, fired = _validate(d, shapes)
    assert not conforms
    assert "MaxCountConstraintComponent" in fired, fired


def test_datatype_is_enforced(eutranetwork):
    """The YANG type became a constraint that actually rejects."""
    shapes, cls, path = eutranetwork
    d = Graph()
    d.add((URIRef("urn:ex:n"), RDF.type, cls))
    d.add((URIRef("urn:ex:n"), path, Literal(42)))    # xsd:string expected
    conforms, fired = _validate(d, shapes)
    assert not conforms
    assert "DatatypeConstraintComponent" in fired, fired


def test_an_empty_data_graph_conforms_to_anything(eutranetwork):
    """Documents the null-only case explicitly, so nobody later 'simplifies' the
    tests above into validating nothing and reads the green as meaningful."""
    shapes, _, _ = eutranetwork
    conforms, fired = _validate(Graph(), shapes)
    assert conforms and not fired


# --- enums and mandatory, on a shape that has them ------------------------

@pytest.fixture(scope="module")
def enum_case(merged_shapes):
    """A real shape carrying both an sh:in enum and mandatory siblings."""
    ns = rdflib.Namespace(
        "https://semantics.ericsson.com/yang/_3gpp-5g-common-yang-types#")
    shape = URIRef("https://semantics.ericsson.com/shapes/"
                   "_3gpp-5g-common-yang-types#CaraConfiguration")
    proto = ns["CaraConfiguration.protocol"]
    mandatory, allowed = [], None
    for ps in merged_shapes.objects(shape, SH.property):
        p = next(merged_shapes.objects(ps, SH.path))
        if any(int(m) >= 1 for m in merged_shapes.objects(ps, SH.minCount)):
            mandatory.append(p)
        if p == proto:
            lst = next(merged_shapes.objects(ps, SH["in"]), None)
            if lst is not None:
                allowed = [str(v) for v in Collection(merged_shapes, lst)]
    assert allowed, "fixture shape has no sh:in enum -- cannot test enums"
    assert mandatory, "fixture shape has no mandatory property -- cannot test minCount"
    return merged_shapes, ns.CaraConfiguration, proto, mandatory, allowed


def test_mandatory_property_is_enforced(enum_case):
    """YANG `mandatory true` became a constraint that actually rejects. Found by
    accident first: a minimal instance was rejected by MinCount on two siblings."""
    shapes, cls, proto, mandatory, allowed = enum_case
    d = Graph()
    d.add((URIRef("urn:ex:i"), RDF.type, cls))
    d.add((URIRef("urn:ex:i"), proto, Literal(allowed[0])))   # mandatory omitted
    conforms, fired = _validate(d, shapes)
    assert not conforms
    assert "MinCountConstraintComponent" in fired, fired


def test_enum_rejects_a_value_outside_the_list(enum_case):
    shapes, cls, proto, mandatory, allowed = enum_case
    d = Graph()
    d.add((URIRef("urn:ex:i"), RDF.type, cls))
    for p in mandatory:
        d.add((URIRef("urn:ex:i"), p, Literal("x")))
    d.add((URIRef("urn:ex:i"), proto, Literal("__not_in_the_enum__")))
    conforms, fired = _validate(d, shapes)
    assert not conforms
    assert "InConstraintComponent" in fired, fired


def test_enum_accepts_a_value_inside_the_list(enum_case):
    """The other direction, without which the test above could pass on a shape
    that rejects everything.

    Asserts the *absence of an sh:in violation* rather than overall conformance:
    the mandatory siblings carry sh:pattern regexes that a placeholder value does
    not satisfy, so the instance legitimately fails for an unrelated reason. That
    distinction is the whole point -- an earlier version of this check read the
    pattern failure as an enum failure.
    """
    shapes, cls, proto, mandatory, allowed = enum_case
    d = Graph()
    d.add((URIRef("urn:ex:i"), RDF.type, cls))
    for p in mandatory:
        d.add((URIRef("urn:ex:i"), p, Literal("x")))
    d.add((URIRef("urn:ex:i"), proto, Literal(allowed[0])))
    _, fired = _validate(d, shapes)
    assert "InConstraintComponent" not in fired, (
        f"an allowed enum value was rejected by sh:in; fired={fired}")


def test_pattern_is_enforced(enum_case):
    """sh:pattern rejects too -- observed via the placeholder value above."""
    shapes, cls, proto, mandatory, allowed = enum_case
    d = Graph()
    d.add((URIRef("urn:ex:i"), RDF.type, cls))
    for p in mandatory:
        d.add((URIRef("urn:ex:i"), p, Literal("x")))
    d.add((URIRef("urn:ex:i"), proto, Literal(allowed[0])))
    conforms, fired = _validate(d, shapes)
    assert not conforms
    assert "PatternConstraintComponent" in fired, fired
