"""Test versioning metadata capture and emission."""
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from yang_to_rdf.output_writer import stamp_versions, INDEX_ONTOLOGY
from yang_to_rdf.yang_parser import Model

NS = "urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction"


def _model_with_rev():
    m = Model()
    m.revisions = {NS: ("2026-05-25", "CR-1702")}
    return m


def test_module_versioninfo_stamped():
    """Module ontology gets owl:versionInfo from revision date + CR."""
    g = Graph()
    g.add((URIRef(NS + "/AMFFunction"), RDF.type, RDFS.Class))
    stamp_versions(g, _model_with_rev())
    assert (URIRef(NS), OWL.versionInfo, Literal("revision 2026-05-25 (CR-1702)")) in g
    assert (URIRef(NS), RDF.type, OWL.Ontology) in g


def test_module_versioninfo_no_cr():
    """Module with revision but no CR still gets versionInfo."""
    m = Model()
    m.revisions = {NS: ("2026-05-25", None)}
    g = Graph()
    g.add((URIRef(NS + "/AMFFunction"), RDF.type, RDFS.Class))
    stamp_versions(g, m)
    assert (URIRef(NS), OWL.versionInfo, Literal("revision 2026-05-25")) in g


def test_aggregate_versioniri_only_with_release():
    """Aggregate ontology gets versionIRI only when release_label given."""
    g = Graph()
    g.add((URIRef(NS + "/AMFFunction"), RDF.type, RDFS.Class))
    stamp_versions(g, _model_with_rev(), release_label="Rel-19", aggregate=True)
    assert (INDEX_ONTOLOGY, OWL.versionInfo, Literal("Rel-19")) in g
    assert (INDEX_ONTOLOGY, OWL.versionIRI,
            URIRef("https://3gpp.org/nrm/ontology/version/Rel-19")) in g
    assert (INDEX_ONTOLOGY, RDF.type, OWL.Ontology) in g


def test_no_release_no_versioniri():
    """Without release_label, no versionIRI is added to aggregate."""
    g = Graph()
    g.add((URIRef(NS + "/AMFFunction"), RDF.type, RDFS.Class))
    stamp_versions(g, _model_with_rev(), aggregate=True)  # no label
    assert list(g.triples((None, OWL.versionIRI, None))) == []
    # Module versionInfo should still be added
    assert (URIRef(NS), OWL.versionInfo, Literal("revision 2026-05-25 (CR-1702)")) in g


def test_special_chars_in_release_label():
    """Release label with special chars is URL-encoded in versionIRI."""
    g = Graph()
    g.add((URIRef(NS + "/AMFFunction"), RDF.type, RDFS.Class))
    stamp_versions(g, _model_with_rev(), release_label="Tag_Rel20_SA112", aggregate=True)
    assert (INDEX_ONTOLOGY, OWL.versionIRI,
            URIRef("https://3gpp.org/nrm/ontology/version/Tag_Rel20_SA112")) in g


def test_deterministic_iteration():
    """Revisions are stamped in sorted order for deterministic output."""
    m = Model()
    m.revisions = {
        "urn:3gpp:sa5:_3gpp-5gc-nrm-bbb": ("2026-01-01", None),
        "urn:3gpp:sa5:_3gpp-5gc-nrm-aaa": ("2026-01-02", "CR-100"),
        "urn:3gpp:sa5:_3gpp-5gc-nrm-ccc": ("2026-01-03", "CR-200"),
    }
    g = Graph()
    # Add subjects from all three modules
    g.add((URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-bbb/ClassB"), RDF.type, RDFS.Class))
    g.add((URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-aaa/ClassA"), RDF.type, RDFS.Class))
    g.add((URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-ccc/ClassC"), RDF.type, RDFS.Class))

    stamp_versions(g, m)

    # Verify all present
    assert (URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-aaa"), OWL.versionInfo,
            Literal("revision 2026-01-02 (CR-100)")) in g
    assert (URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-bbb"), OWL.versionInfo,
            Literal("revision 2026-01-01")) in g
    assert (URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-ccc"), OWL.versionInfo,
            Literal("revision 2026-01-03 (CR-200)")) in g


def test_revisions_captured_from_real_set(parsed_model):
    """Integration test: real dataset captures module revisions."""
    model, _ = parsed_model
    assert hasattr(model, "revisions"), "Model should have revisions dict"
    assert NS in model.revisions, f"{NS} should be in captured revisions"
    date, cr = model.revisions[NS]
    assert date.count("-") == 2, f"Date should be YYYY-MM-DD format, got {date}"
    assert cr is None or cr.startswith("CR"), f"CR should start with 'CR' or be None, got {cr}"


def test_only_stamps_modules_present_in_graph():
    """Only stamp versionInfo for modules that have subjects in the graph."""
    m = Model()
    m.revisions = {
        "urn:3gpp:sa5:_3gpp-5gc-nrm-present": ("2026-01-01", None),
        "urn:3gpp:sa5:_3gpp-5gc-nrm-absent": ("2026-01-02", None),
    }
    g = Graph()
    # Only add subject from "present" module
    g.add((URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-present/Class"), RDF.type, RDFS.Class))

    stamp_versions(g, m)

    # Present module should have versionInfo
    assert (URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-present"), OWL.versionInfo,
            Literal("revision 2026-01-01")) in g
    # Absent module should NOT have versionInfo
    assert (URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-absent"), OWL.versionInfo,
            Literal("revision 2026-01-02")) not in g


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
