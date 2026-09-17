# tests/test_shacl_converter.py
from rdflib import RDF, URIRef

from tests._shared import cached_shacl_graph as _graph, cls_iri, prop_iri, shp_iri
from yang_to_rdf.shacl_converter import SH

AMF_SHAPE = URIRef(shp_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction"))
AMF = URIRef(cls_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction"))


def test_shape_targets_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    assert (AMF_SHAPE, RDF.type, SH.NodeShape) in g
    assert (AMF_SHAPE, SH.targetClass, AMF) in g


def test_inherited_property_materialized(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    paths = {str(p) for ps in g.objects(AMF_SHAPE, SH.property)
             for p in g.objects(ps, SH.path)}
    assert prop_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction", "userLabel") in paths


def test_datatype_attr_uses_sh_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    tm_shape = URIRef(shp_iri("_3gpp-5gc-nrm-smffunction", "ThresholdMonitor"))
    # ThresholdInfo (from ThresholdInfoGrp) belongs to common-measurements.
    dt = URIRef(cls_iri("_3gpp-common-measurements", "ThresholdInfo"))
    classes = set()
    for ps in g.objects(tm_shape, SH.property):
        for c in g.objects(ps, SH["class"]):
            classes.add(c)
    assert dt in classes


def test_dn_pattern_present(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    patterns = [str(o) for o in g.objects(None, SH.pattern)]
    assert any("=" in p for p in patterns)


# --- the shapes namespace is what prevents a FooShape collision ----------

def test_shape_iri_is_not_a_class_iri(yang_dir, external_yams_dir):
    """Shapes live under <base>shapes/<mod>#, classes under <base>yang/<mod>#, so
    a YANG class genuinely named `AMFFunctionShape` could not collide with the
    shape of `AMFFunction`. Structural, not dependent on the corpus -- no such
    class exists in the 3GPP set (0 of 535), which is exactly why the separation
    must hold by construction rather than by luck."""
    would_have_collided = cls_iri("_3gpp-5gc-nrm-amffunction", "AMFFunctionShape")
    assert str(AMF_SHAPE) != would_have_collided
    assert "/shapes/" in str(AMF_SHAPE)


def test_every_shape_lives_in_the_shapes_namespace(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    shapes = list(g.subjects(RDF.type, SH.NodeShape))
    assert shapes, "no NodeShapes emitted -- the check could not run"
    stray = [str(s) for s in shapes if "/shapes/" not in str(s)]
    assert not stray, f"{len(stray)} of {len(shapes)} shapes outside shapes/"
