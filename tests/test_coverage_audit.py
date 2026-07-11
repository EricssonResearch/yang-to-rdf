"""Coverage audit as a regression gate: the emitted RDF/SHACL must represent
everything the parser found (see scripts/coverage_audit.py for the rationale)."""
from tests._shared import cached_parse, cached_rdf_graph, cached_shacl_graph

from scripts.coverage_audit import audit


def _audit(yang_dir, external_yams_dir):
    model, errors = cached_parse(yang_dir, external_yams_dir)
    rdf = cached_rdf_graph(yang_dir, external_yams_dir)
    shacl = cached_shacl_graph(yang_dir, external_yams_dir)
    return model, errors, audit(model, rdf, shacl)


def test_no_unmodeled_node_kinds(yang_dir, external_yams_dir):
    _, errors, _ = _audit(yang_dir, external_yams_dir)
    unmodeled = [e for e in errors if "unmodeled attribute node kind" in e]
    assert unmodeled == [], f"parser silently skipped node kinds: {unmodeled}"


def test_every_ir_element_present_in_rdf(yang_dir, external_yams_dir):
    _, _, report = _audit(yang_dir, external_yams_dir)
    assert report["rdf_missing_class"] == []
    assert report["rdf_missing_leaf"] == []
    assert report["rdf_missing_attr"] == []


def test_rdf_and_shacl_cover_the_same_classes(yang_dir, external_yams_dir):
    _, _, report = _audit(yang_dir, external_yams_dir)
    assert report["class_without_shape"] == []
    assert report["shape_without_class"] == []
