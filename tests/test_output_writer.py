"""Tests for split-output module partitioning."""
import subprocess
import sys
from pathlib import Path

import pytest

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


@pytest.mark.slow
def test_cli_split_is_default_and_browsable(yang_dir, tmp_path):
    """Full-set integration: file count, browsable sizes, real parse. ~35s."""
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
    # Assert on the PARSED graph, not on bytes: terms serialize as
    # `amf3gpp:AMFFunction` once per-module prefixes are bound, so a substring
    # check would be testing the serialization style rather than the content.
    parsed = Graph()
    parsed.parse(amf, format="turtle")
    assert (URIRef(cls_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction")),
            RDF.type, RDFS.Class) in parsed
    # each module file is small enough to browse (< 2 MB); the old merged file was ~7 MB
    assert all((out / f).stat().st_size < 2_000_000 for f in files)


def test_module_files_bind_the_yang_prefix(tiny_yang_dir, tmp_path):
    """The readability win: a reader sees `ausf3gpp:AUSFFunction`, not a full IRI.

    Runs against the ~8-module tiny set; prefix binding is dataset-size
    independent, so the full 120-module set adds cost and no information.
    """
    out = tmp_path / "prefixed"
    subprocess.run(
        [sys.executable, "-m", "yang_to_rdf.main", tiny_yang_dir, "-o", str(out)],
        check=True,
    )
    text = (out / "_3gpp-5gc-nrm-ausffunction_rdf.ttl").read_text()
    assert "@prefix ausf3gpp:" in text
    assert "ausf3gpp:AUSFFunction." in text
    shapes = (out / "_3gpp-5gc-nrm-ausffunction_shacl.ttl").read_text()
    assert "@prefix ausf3gpp-shapes:" in shapes


def test_output_filenames_use_the_declared_module_name(parsed_model):
    """Filenames come from the module name, not the YANG namespace URN, so the
    two upstream discrepancies in this set are corrected (spec §4).

    Uses the session-scoped parsed model rather than shelling out to the CLI: the
    filename is exactly module_stem(module_iri), so a subprocess over 120 modules
    would cost ~60s to test a pure function.
    """
    model, _ = parsed_model
    stems = {module_stem(m) for m in model.module_iris}
    assert stems, "no modules parsed -- the check could not run"
    assert "_3gpp-5gc-nrm-externalseppfunction" in stems
    assert "_3gpp-nr-nrm-nrsectorcarrier" in stems
    # the namespace-derived spellings must be gone
    assert not [s for s in stems if "extternal" in s]
    assert not [s for s in stems if "nrnetwork-nrsectorcarrier" in s]


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


# --- Turtle prefixes derived from the source YANG ------------------------

def test_turtle_prefixes_come_from_the_yang_prefix_statement(parsed_model):
    """YANG already declares a short prefix per module (RFC 7950 §7.1.4), so we
    bind that rather than inventing one."""
    from yang_to_rdf.output_writer import turtle_prefixes
    model, _ = parsed_model
    pfx = turtle_prefixes(model)
    assert pfx["amf3gpp"] == namespace_base(mod_iri("_3gpp-5gc-nrm-amffunction"))
    assert pfx["mf3gpp"] == namespace_base(mod_iri("_3gpp-common-managed-function"))
    assert "amf3gpp-shapes" in pfx


def test_every_module_gets_a_prefix_and_they_are_unique(parsed_model):
    """Counted both ways, so a module silently losing its prefix fails loudly."""
    from yang_to_rdf.output_writer import turtle_prefixes
    model, _ = parsed_model
    pfx = turtle_prefixes(model)
    assert len(pfx) == 2 * len(model.module_iris), (
        f"{len(pfx)} prefixes for {len(model.module_iris)} modules "
        f"(expected 2 each: terms + shapes)")
    assert len(set(pfx.values())) == len(pfx), "two prefixes share a namespace"


def test_prefix_collisions_are_resolved_deterministically():
    """YANG only guarantees prefix uniqueness within one module's import scope,
    so an arbitrary module set CAN collide. Real 3GPP Rel-19 has 0 collisions,
    so this needs constructed input to reach the code at all."""
    from yang_to_rdf.output_writer import turtle_prefixes
    from yang_to_rdf.yang_parser import Model, ModuleMeta
    a, b = mod_iri("mod-a"), mod_iri("mod-b")
    m = Model()
    m.module_iris = {a, b}
    m.module_meta = {a: ModuleMeta(name="mod-a", prefix="same"),
                     b: ModuleMeta(name="mod-b", prefix="same")}
    pfx = turtle_prefixes(m)
    assert "same" in pfx and "same-2" in pfx
    # deterministic: sorted module order decides who keeps the bare prefix
    assert pfx["same"] == namespace_base(a)
    assert pfx["same-2"] == namespace_base(b)


def test_a_module_without_a_prefix_falls_back_to_its_name():
    from yang_to_rdf.output_writer import turtle_prefixes
    from yang_to_rdf.yang_parser import Model, ModuleMeta
    a = mod_iri("mod-a")
    m = Model()
    m.module_iris = {a}
    m.module_meta = {a: ModuleMeta(name="mod-a", prefix="")}
    assert turtle_prefixes(m)["mod-a"] == namespace_base(a)


def test_bind_used_prefixes_binds_only_what_the_graph_references():
    """Regression guard for a 10x slowdown. Binding every module prefix on every
    graph took Rel-19 conversion from 35s to 354s, because rdflib consults each
    binding for every term it serializes. This pins the structural property that
    prevents it -- a timing assertion would be flaky, but "binds a small subset"
    is exact."""
    from yang_to_rdf.output_writer import bind_used_prefixes
    used = mod_iri("_3gpp-5gc-nrm-amffunction")
    unused = mod_iri("_3gpp-common-managed-element")
    prefixes = {
        "amf3gpp": namespace_base(used),
        "me3gpp": namespace_base(unused),
        "other3gpp": namespace_base(mod_iri("_3gpp-common-subnetwork")),
    }
    g = Graph()
    g.add((URIRef(cls_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction")),
           RDF.type, RDFS.Class))

    bound = bind_used_prefixes(g, prefixes)

    assert bound == 1, f"bound {bound} of {len(prefixes)}, expected only the used one"
    names = {p for p, _ in g.namespaces()}
    assert "amf3gpp" in names
    assert "me3gpp" not in names and "other3gpp" not in names


def test_bind_used_prefixes_reports_zero_when_nothing_matches():
    """A count of 0 is a legitimate answer and must be distinguishable from
    'the function did not run'."""
    from yang_to_rdf.output_writer import bind_used_prefixes
    g = Graph()
    g.add((URIRef("https://example.org/other#X"), RDF.type, RDFS.Class))
    assert bind_used_prefixes(g, {"amf3gpp": namespace_base(mod_iri("m"))}) == 0
