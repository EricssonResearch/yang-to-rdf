# tests/test_shacl_converter.py
import glob, os
from rdflib import RDF, URIRef
from yang_to_rdf.yang_parser import parse
from yang_to_rdf.shacl_converter import YangToSHACLConverter, SH

def _graph(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    model, _ = parse(files, [yang_dir, external_yams_dir])
    return YangToSHACLConverter(model).convert()

AMF_SHAPE = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunctionShape")
AMF = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction")

def test_shape_targets_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    assert (AMF_SHAPE, RDF.type, SH.NodeShape) in g
    assert (AMF_SHAPE, SH.targetClass, AMF) in g

def test_inherited_property_materialized(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    paths = {str(p) for ps in g.objects(AMF_SHAPE, SH.property)
             for p in g.objects(ps, SH.path)}
    assert any(p.endswith("/AMFFunction/userLabel") for p in paths)

def test_datatype_attr_uses_sh_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    tm_shape = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/ThresholdMonitorShape")
    dt = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/thresholdInfoList")
    classes = set()
    for ps in g.objects(tm_shape, SH.property):
        for c in g.objects(ps, SH["class"]):
            classes.add(c)
    assert dt in classes

def test_dn_pattern_present(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    patterns = [str(o) for o in g.objects(None, SH.pattern)]
    assert any("=" in p for p in patterns)
