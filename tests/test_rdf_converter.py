# tests/test_rdf_converter.py
import glob, os
from rdflib import RDF, RDFS, Literal, URIRef
from rdflib.namespace import OWL
from yang_to_rdf.yang_parser import parse
from yang_to_rdf.rdf_converter import YangToRDFConverter, NRM

def _graph(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    model, _ = parse(files, [yang_dir, external_yams_dir])
    return YangToRDFConverter(model).convert()

AMF = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction")

def test_amffunction_is_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    assert (AMF, RDF.type, RDFS.Class) in g

def test_amffunction_subclass_managed_function(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    assert (AMF, RDFS.subClassOf, NRM.ManagedFunction) in g

def test_datatype_is_class_and_linked(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    tm = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/ThresholdMonitor")
    dt = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/thresholdInfoList")
    assert (dt, RDF.type, RDFS.Class) in g
    prop = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/ThresholdMonitor/thresholdInfoList")
    assert (prop, RDF.type, OWL.ObjectProperty) in g
    assert (prop, RDFS.range, dt) in g
    assert (prop, RDFS.domain, tm) in g
    assert (tm, NRM.hasAttribute, dt) in g

def test_dn_ref_is_object_property_without_range(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    ref = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction/aMFSetRef")
    assert (ref, RDF.type, OWL.ObjectProperty) in g
    assert (ref, NRM.isReference, Literal(True)) in g
    assert list(g.objects(ref, RDFS.range)) == []

def test_typedef_is_datatype_not_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    dn = URIRef("urn:3gpp:sa5:_3gpp-common-yang-types/DistinguishedName")
    assert (dn, RDF.type, RDFS.Datatype) in g
    assert (dn, RDF.type, RDFS.Class) not in g

def test_invariant_leaf_annotated(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    prop = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-ausffunction/ausfInfo/nFSrvGroupId")
    assert (prop, NRM.isInvariant, Literal(True)) in g
