"""Tests for split-output module partitioning."""
import subprocess
import sys
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from tests._shared import BASE, Y2R, cls_iri, mod_iri, prop_iri, shp_iri
from yang_to_rdf.namespace import (
    class_iri,
    module_iri,
    module_stem,
    namespace_base,
)
from yang_to_rdf.output_writer import module_ns, module_prefix_map, split_graph

MOD_A = mod_iri("_3gpp-5gc-nrm-amffunction")
MOD_B = mod_iri("_3gpp-common-managed-element")
PMAP = module_prefix_map(BASE, {MOD_A, MOD_B})


def test_module_ns_matches_the_ontology_iri_and_its_hash_terms():
    assert module_ns(URIRef(MOD_A), PMAP) == MOD_A
    assert module_ns(URIRef(cls_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction")),
                     PMAP) == MOD_A
    assert module_ns(URIRef(prop_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction",
                                     "userLabel")), PMAP) == MOD_A
    assert module_stem(MOD_A) == "_3gpp-5gc-nrm-amffunction"


def test_minted_vocabulary_belongs_to_no_module():
    assert module_ns(URIRef(str(Y2R.nameContains)), PMAP) is None


def test_shape_iris_route_to_the_owning_module():
    """Shapes live under <base>shapes/<mod>#, a different prefix, but must land in
    the same module's file so a module's three layers stay together."""
    s = URIRef(shp_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction"))
    assert module_ns(s, PMAP) == MOD_A


def test_a_module_iri_that_prefixes_another_does_not_steal_its_terms():
    """'<base>yang/mod' must not capture '<base>yang/mod-extra#X'. Requiring the
    '#' delimiter is what prevents it; the old '/'-based match had the same
    protection, and this pins it so a refactor cannot quietly drop it."""
    short, long_ = module_iri(BASE, "mod"), module_iri(BASE, "mod-extra")
    pmap = module_prefix_map(BASE, {short, long_})
    term = class_iri(namespace_base(long_), "X")
    assert module_ns(URIRef(term), pmap) == long_


def test_module_ns_is_base_agnostic():
    """A different --base-iri partitions just as correctly."""
    other = module_iri("https://example.org/nrm/", "foofunction")
    pmap = module_prefix_map("https://example.org/nrm/", {other})
    assert module_ns(URIRef(class_iri(namespace_base(other), "FooFunction")),
                     pmap) == other
    assert module_stem(other) == "foofunction"


def test_split_routes_triples_by_subject_module():
    g = Graph()
    amf = URIRef(cls_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction"))
    me = URIRef(cls_iri("_3gpp-common-managed-element", "ManagedElement"))
    contains = URIRef(str(Y2R.nameContains))
    g.add((amf, RDF.type, RDFS.Class))
    g.add((me, contains, amf))                       # cross-module edge, subject = me
    g.add((contains, RDF.type, OWL.ObjectProperty))  # vocab -> index
    mods, index = split_graph(g, PMAP, BASE)
    assert (amf, RDF.type, RDFS.Class) in mods[MOD_A]
    assert (me, contains, amf) in mods[MOD_B]        # lives with its SUBJECT's module
    assert (contains, RDF.type, OWL.ObjectProperty) in index


def test_split_keeps_bnode_closure_with_owner():
    # a SHACL-like shape: shape (shapes namespace) -> bnode -> path (yang namespace)
    g = Graph()
    shape = URIRef(shp_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction"))
    path_target = URIRef(prop_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction",
                                  "userLabel"))
    ps = BNode()
    SH_PROPERTY = URIRef("http://www.w3.org/ns/shacl#property")
    SH_PATH = URIRef("http://www.w3.org/ns/shacl#path")
    g.add((shape, SH_PROPERTY, ps))
    g.add((ps, SH_PATH, path_target))
    mods, index = split_graph(g, PMAP, BASE)
    assert (shape, SH_PROPERTY, ps) in mods[MOD_A]
    assert (ps, SH_PATH, path_target) in mods[MOD_A]
    assert all(t[0] != ps for t in index)  # bnode not orphaned to index


def test_no_triple_dropped():
    g = Graph()
    g.add((URIRef(cls_iri("_3gpp-5gc-nrm-amffunction", "X")), RDF.type, RDFS.Class))
    g.add((URIRef("https://ex/orphan"), RDF.value, Literal("z")))
    mods, index = split_graph(g, PMAP, BASE)
    # every original triple present somewhere (owl:Ontology/imports are additive)
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
    assert b"#AMFFunction" in amf.read_bytes()
    # each module file is small enough to browse (< 2 MB); the old merged file was ~7 MB
    assert all((out / f).stat().st_size < 2_000_000 for f in files)


def test_output_filenames_use_the_declared_module_name(yang_dir, tmp_path):
    """Filenames come from the module name, not the YANG namespace URN, so the
    two upstream discrepancies in this set are corrected (spec §4)."""
    out = tmp_path / "names"
    subprocess.run(
        [sys.executable, "-m", "yang_to_rdf.main", yang_dir, "-o", str(out)],
        check=True,
    )
    names = {p.name for p in out.glob("*.ttl")}
    assert names, "no output written -- the check could not run"
    assert "_3gpp-5gc-nrm-externalseppfunction_rdf.ttl" in names
    assert "_3gpp-nr-nrm-nrsectorcarrier_rdf.ttl" in names
    # the namespace-derived spellings must be gone
    assert not [n for n in names if "extternal" in n]
    assert not [n for n in names if "nrnetwork-nrsectorcarrier" in n]


def test_cli_single_file_flag(tiny_yang_dir, tmp_path):
    out = tmp_path / "single"
    stem = Path(tiny_yang_dir).name
    subprocess.run(
        [sys.executable, "-m", "yang_to_rdf.main", tiny_yang_dir, "-o", str(out),
         "--single-file"],
        check=True,
    )
    assert (out / f"{stem}_rdf.ttl").is_file()
    assert not (out / "index.ttl").exists()
    # split-mode per-module file must NOT appear in single-file mode
    assert not (out / "_3gpp-5gc-nrm-ausffunction_rdf.ttl").exists()
