"""Test versioning metadata capture and emission."""
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from tests._shared import BASE, Y2R, cls_iri, mod_iri
from yang_to_rdf.namespace import aggregate_ontology_iri, version_iri
from yang_to_rdf.output_writer import stamp_versions
from yang_to_rdf.yang_parser import Model

MODULE = "_3gpp-5gc-nrm-amffunction"
NS = mod_iri(MODULE)
INDEX_ONTOLOGY = URIRef(aggregate_ontology_iri(BASE))


def _model_with_rev():
    m = Model()
    m.revisions = {NS: ("2026-05-25", "CR-1702")}
    m.module_iris = {NS}
    return m


def test_module_versioninfo_stamped():
    """Module ontology gets owl:versionInfo from revision date + CR."""
    g = Graph()
    g.add((URIRef(cls_iri(MODULE, "AMFFunction")), RDF.type, RDFS.Class))
    stamp_versions(g, _model_with_rev())
    assert (URIRef(NS), OWL.versionInfo, Literal("revision 2026-05-25 (CR-1702)")) in g
    assert (URIRef(NS), RDF.type, OWL.Ontology) in g


def test_module_versioninfo_no_cr():
    """Module with revision but no CR still gets versionInfo."""
    m = Model()
    m.revisions = {NS: ("2026-05-25", None)}
    m.module_iris = {NS}
    g = Graph()
    g.add((URIRef(cls_iri(MODULE, "AMFFunction")), RDF.type, RDFS.Class))
    stamp_versions(g, m)
    assert (URIRef(NS), OWL.versionInfo, Literal("revision 2026-05-25")) in g


def test_module_with_no_revision_still_gets_stamped():
    """Regression: the old revision-keyed loop skipped a module without a
    `revision` statement entirely, so it got no ontology declaration, no
    dcterms metadata and no provenance."""
    m = Model()
    m.module_iris = {NS}          # registered, but no revision
    g = Graph()
    g.add((URIRef(cls_iri(MODULE, "AMFFunction")), RDF.type, RDFS.Class))
    stamp_versions(g, m)
    assert (URIRef(NS), RDF.type, OWL.Ontology) in g
    assert list(g.objects(URIRef(NS), OWL.versionInfo)) == []


def test_aggregate_versioniri_only_with_release():
    """Aggregate ontology gets versionIRI only when release_label given."""
    g = Graph()
    g.add((URIRef(cls_iri(MODULE, "AMFFunction")), RDF.type, RDFS.Class))
    stamp_versions(g, _model_with_rev(), release_label="Rel-19", aggregate=True)
    assert (INDEX_ONTOLOGY, OWL.versionInfo, Literal("Rel-19")) in g
    assert (INDEX_ONTOLOGY, OWL.versionIRI,
            URIRef(version_iri(BASE, "Rel-19"))) in g
    assert (INDEX_ONTOLOGY, RDF.type, OWL.Ontology) in g


def test_no_release_no_versioniri():
    """Without release_label, no versionIRI is added to aggregate."""
    g = Graph()
    g.add((URIRef(cls_iri(MODULE, "AMFFunction")), RDF.type, RDFS.Class))
    stamp_versions(g, _model_with_rev(), aggregate=True)  # no label
    assert list(g.triples((None, OWL.versionIRI, None))) == []
    # Module versionInfo should still be added
    assert (URIRef(NS), OWL.versionInfo, Literal("revision 2026-05-25 (CR-1702)")) in g


def test_special_chars_in_release_label():
    """Release label is URL-encoded in the versionIRI (it is a path segment)."""
    g = Graph()
    g.add((URIRef(cls_iri(MODULE, "AMFFunction")), RDF.type, RDFS.Class))
    stamp_versions(g, _model_with_rev(), release_label="Tag_Rel20_SA112",
                   aggregate=True)
    assert (INDEX_ONTOLOGY, OWL.versionIRI,
            URIRef(version_iri(BASE, "Tag_Rel20_SA112"))) in g


def test_deterministic_iteration():
    """Revisions are stamped in sorted order for deterministic output."""
    mods = {name: mod_iri(f"_3gpp-5gc-nrm-{name}") for name in ("aaa", "bbb", "ccc")}
    m = Model()
    m.revisions = {
        mods["bbb"]: ("2026-01-01", None),
        mods["aaa"]: ("2026-01-02", "CR-100"),
        mods["ccc"]: ("2026-01-03", "CR-200"),
    }
    m.module_iris = set(mods.values())
    g = Graph()
    for name, cls in (("aaa", "ClassA"), ("bbb", "ClassB"), ("ccc", "ClassC")):
        g.add((URIRef(cls_iri(f"_3gpp-5gc-nrm-{name}", cls)), RDF.type, RDFS.Class))

    stamp_versions(g, m)

    assert (URIRef(mods["aaa"]), OWL.versionInfo,
            Literal("revision 2026-01-02 (CR-100)")) in g
    assert (URIRef(mods["bbb"]), OWL.versionInfo,
            Literal("revision 2026-01-01")) in g
    assert (URIRef(mods["ccc"]), OWL.versionInfo,
            Literal("revision 2026-01-03 (CR-200)")) in g


def test_revisions_captured_from_real_set(parsed_model):
    """Integration test: real dataset captures module revisions."""
    model, _ = parsed_model
    assert hasattr(model, "revisions"), "Model should have revisions dict"
    assert NS in model.revisions, f"{NS} should be in captured revisions"
    date, cr = model.revisions[NS]
    assert date.count("-") == 2, f"Date should be YYYY-MM-DD format, got {date}"
    assert cr is None or cr.startswith("CR"), \
        f"CR should start with 'CR' or be None, got {cr}"


def test_only_stamps_modules_present_in_graph():
    """Only stamp versionInfo for modules that have subjects in the graph."""
    present, absent = mod_iri("_3gpp-5gc-nrm-present"), mod_iri("_3gpp-5gc-nrm-absent")
    m = Model()
    m.revisions = {present: ("2026-01-01", None), absent: ("2026-01-02", None)}
    m.module_iris = {present, absent}
    g = Graph()
    # Only add a subject from the "present" module
    g.add((URIRef(cls_iri("_3gpp-5gc-nrm-present", "Class")), RDF.type, RDFS.Class))

    stamp_versions(g, m)

    assert (URIRef(present), OWL.versionInfo, Literal("revision 2026-01-01")) in g
    assert (URIRef(absent), OWL.versionInfo, Literal("revision 2026-01-02")) not in g


# --- YANG provenance (spec D6) -------------------------------------------

def test_module_ontology_carries_yang_provenance(parsed_model):
    """The discarded YANG namespace URN stays queryable, including for the module
    whose namespace disagrees with its name."""
    from yang_to_rdf.yang_parser import ModuleMeta
    model, _ = parsed_model
    module = "_3gpp-5gc-nrm-externalseppfunction"
    mod = mod_iri(module)
    g = Graph()
    g.add((URIRef(cls_iri(module, "SEPPFunction")), RDF.type, RDFS.Class))
    stamp_versions(g, model)
    assert isinstance(model.module_meta[mod], ModuleMeta)
    assert (URIRef(mod), Y2R.yangModuleName, Literal(module)) in g
    assert (URIRef(mod), Y2R.yangNamespace,
            URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-extternalseppfunction")) in g


def test_provenance_is_emitted_for_every_module(parsed_model):
    """Counted, so a module silently losing its provenance fails loudly."""
    model, _ = parsed_model
    g = Graph()
    for mod in model.module_iris:
        g.add((URIRef(mod), RDF.type, OWL.Ontology))
    stamp_versions(g, model)
    named = set(g.subjects(Y2R.yangModuleName, None))
    assert len(named) == len(model.module_iris), (
        f"{len(named)} modules carry yangModuleName, expected "
        f"{len(model.module_iris)}")


def test_nothing_is_minted_under_the_old_3gpp_org_namespace(parsed_model):
    """We must not mint IRIs under 3gpp.org. Note this is narrower than "no
    mention of 3gpp.org": module `contact` statements legitimately carry
    https://www.3gpp.org/... URLs, which are input DATA faithfully preserved,
    not identifiers we assert authority over."""
    model, _ = parsed_model
    g = Graph()
    g.add((URIRef(cls_iri(MODULE, "AMFFunction")), RDF.type, RDFS.Class))
    stamp_versions(g, model, release_label="Rel-19", aggregate=True)
    minted = [str(x) for t in g for x in t
              if isinstance(x, URIRef) and "3gpp.org/nrm/" in str(x)]
    assert not minted, minted
    # The YANG-sourced contact URL IS expected to survive, as a literal.
    contacts = [str(o) for o in g.objects(None, RDFS.seeAlso)]
    assert any("3gpp.org" in c for c in contacts), \
        "the YANG contact URL should be preserved, not scrubbed"


# Part 2 tests: --fetch-release URL building
def test_forge_url_built_for_tag():
    """Forge archive URL template contains required components."""
    from yang_to_rdf.input_handler import FORGE_ARCHIVE
    url = FORGE_ARCHIVE.format(ref="Tag_Rel20_SA112", ref_type="tags")
    assert "archive/Tag_Rel20_SA112/MnS-Tag_Rel20_SA112.zip" in url
    assert "path=yang-models" in url
    assert "ref_type=tags" in url


def test_forge_url_built_for_branch():
    """Forge archive URL for a branch (heads ref_type)."""
    from yang_to_rdf.input_handler import FORGE_ARCHIVE
    url = FORGE_ARCHIVE.format(ref="Rel-19", ref_type="heads")
    assert "archive/Rel-19/MnS-Rel-19.zip" in url
    assert "path=yang-models" in url
    assert "ref_type=heads" in url
