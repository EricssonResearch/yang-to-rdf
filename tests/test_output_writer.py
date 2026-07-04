"""Tests for split-output module partitioning."""
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL
from yang_to_rdf.output_writer import split_graph, module_urn, module_stem
import subprocess
import sys
from pathlib import Path

NS_A = "urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction"
NS_B = "urn:3gpp:sa5:_3gpp-common-managed-element"


def test_module_urn_and_stem():
    assert module_urn(URIRef(NS_A + "/AMFFunction")) == NS_A
    assert module_urn(URIRef(NS_A + "/AMFFunction/userLabel")) == NS_A
    assert module_urn(URIRef("https://3gpp.org/nrm/vocab#nameContains")) is None
    assert module_stem(NS_A) == "_3gpp-5gc-nrm-amffunction"


def test_split_routes_triples_by_subject_module():
    g = Graph()
    amf = URIRef(NS_A + "/AMFFunction")
    me = URIRef(NS_B + "/ManagedElement")
    NRM = URIRef("https://3gpp.org/nrm/vocab#nameContains")
    g.add((amf, RDF.type, RDFS.Class))
    g.add((me, NRM, amf))  # cross-module edge, subject = me
    g.add((NRM, RDF.type, OWL.ObjectProperty))  # vocab -> index
    mods, index = split_graph(g)
    assert (amf, RDF.type, RDFS.Class) in mods[NS_A]
    assert (me, NRM, amf) in mods[NS_B]  # lives with its SUBJECT's module
    assert (NRM, RDF.type, OWL.ObjectProperty) in index


def test_split_keeps_bnode_closure_with_owner():
    # a SHACL-like shape: shape (module URIRef) -> bnode -> path
    g = Graph()
    shape = URIRef(NS_A + "/AMFFunctionShape")
    ps = BNode()
    SH = URIRef("http://www.w3.org/ns/shacl#property")
    PATH = URIRef("http://www.w3.org/ns/shacl#path")
    g.add((shape, SH, ps))
    g.add((ps, PATH, URIRef(NS_A + "/AMFFunction/userLabel")))
    mods, index = split_graph(g)
    assert (shape, SH, ps) in mods[NS_A]
    assert (ps, PATH, URIRef(NS_A + "/AMFFunction/userLabel")) in mods[NS_A]
    assert len(index) == 0 or all(t[0] != ps for t in index)  # bnode not orphaned to index


def test_no_triple_dropped():
    g = Graph()
    g.add((URIRef(NS_A + "/X"), RDF.type, RDFS.Class))
    g.add((URIRef("https://ex/orphan"), RDF.value, Literal("z")))
    mods, index = split_graph(g)
    # every original triple present somewhere (owl:Ontology/imports triples are additive)
    for t in g:
        assert t in index or any(t in mg for mg in mods.values())


def test_cli_split_is_default_and_browsable(yang_dir, tmp_path):
    out = tmp_path / "split"
    subprocess.run(
        [sys.executable, "-m", "yang_to_rdf.main", yang_dir, "-o", str(out)],
        check=True,
    )
    files = sorted(p.name for p in out.glob("*.ttl"))
    assert (out / "index.ttl").is_file()
    # one per module per layer -> many small files, none huge
    assert len(files) > 100
    amf = out / "_3gpp-5gc-nrm-amffunction_rdf.ttl"
    assert amf.is_file()
    assert b"/AMFFunction" in amf.read_bytes()
    # each module file is small enough to browse (< 2 MB); the old merged file was ~7 MB
    assert all((out / f).stat().st_size < 2_000_000 for f in files)


def test_cli_single_file_flag(tiny_yang_dir, tmp_path):
    out = tmp_path / "single"
    stem = Path(tiny_yang_dir).name
    subprocess.run(
        [sys.executable, "-m", "yang_to_rdf.main", tiny_yang_dir, "-o", str(out), "--single-file"],
        check=True,
    )
    assert (out / f"{stem}_rdf.ttl").is_file()
    assert not (out / "index.ttl").exists()
    # split-mode per-module file must NOT appear in single-file mode
    assert not (out / "_3gpp-5gc-nrm-ausffunction_rdf.ttl").exists()
