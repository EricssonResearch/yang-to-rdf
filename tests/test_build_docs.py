"""The doc graph must have exactly one owl:Ontology (the aggregate) so an
ontology-documentation tool has a single, correctly-titled subject; every module
ontology is demoted to an owl:imports. pyLODE itself is not exercised here (it is
an optional dev tool); we test the graph shaping it depends on."""
from rdflib import RDF, URIRef
from rdflib.namespace import DCTERMS, OWL

from scripts.build_docs import build_doc_graph
from yang_to_rdf.output_writer import INDEX_ONTOLOGY
from tests._shared import cached_parse


def test_doc_graph_has_single_titled_ontology(yang_dir, external_yams_dir):
    model, _ = cached_parse(yang_dir, external_yams_dir)
    g = build_doc_graph(model, release_label="Rel-19")

    ontologies = list(g.subjects(RDF.type, OWL.Ontology))
    assert ontologies == [INDEX_ONTOLOGY], f"expected only the aggregate, got {ontologies}"

    # It must carry a title (pyLODE requires one).
    assert g.value(INDEX_ONTOLOGY, DCTERMS.title) is not None
    # Demoted modules are still referenced as imports (nothing orphaned).
    assert len(list(g.objects(INDEX_ONTOLOGY, OWL.imports))) > 100

    # Classes survive the demotion (a known IOC is still present with its label).
    from rdflib.namespace import RDFS
    amf = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction")
    assert (amf, RDF.type, RDFS.Class) in g
    assert g.value(amf, RDFS.label) is not None


def test_labels_are_globally_unique(yang_dir, external_yams_dir):
    """pyLODE builds HTML anchors from labels, so they must be unique across the
    whole graph despite heavy local-name reuse across modules."""
    from collections import Counter
    from rdflib.namespace import RDFS

    model, _ = cached_parse(yang_dir, external_yams_dir)
    g = build_doc_graph(model, release_label=None)
    counts = Counter(str(o) for _, _, o in g.triples((None, RDFS.label, None)))
    dups = {k: v for k, v in counts.items() if v > 1}
    assert dups == {}, f"duplicate rdfs:labels break doc anchors: {list(dups)[:5]}"
