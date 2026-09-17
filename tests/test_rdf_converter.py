# tests/test_rdf_converter.py
from rdflib import RDF, RDFS, Literal, URIRef
from rdflib.namespace import OWL

from tests._shared import Y2R, cached_rdf_graph as _graph, cls_iri, prop_iri

AMF = URIRef(cls_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction"))


def test_amffunction_is_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    assert (AMF, RDF.type, RDFS.Class) in g


def test_amffunction_subclass_managed_function(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    assert (AMF, RDFS.subClassOf, Y2R.ManagedFunction) in g


def test_datatype_is_class_and_linked(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    # ThresholdMonitor is in one module, but ThresholdInfo (from ThresholdInfoGrp)
    # belongs to the grouping's home module (_3gpp-common-measurements).
    tm = URIRef(cls_iri("_3gpp-5gc-nrm-smffunction", "ThresholdMonitor"))
    dt = URIRef(cls_iri("_3gpp-common-measurements", "ThresholdInfo"))
    assert (dt, RDF.type, RDFS.Class) in g
    # The property is class-scoped on ThresholdMonitor (the owning class); the
    # leaf name stays thresholdInfoList.
    prop = URIRef(prop_iri("_3gpp-5gc-nrm-smffunction", "ThresholdMonitor",
                           "thresholdInfoList"))
    assert (prop, RDF.type, OWL.ObjectProperty) in g
    assert (prop, RDFS.range, dt) in g
    assert (prop, RDFS.domain, tm) in g
    assert (tm, Y2R.hasAttribute, dt) in g


def test_dn_ref_is_object_property_without_range(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    ref = URIRef(prop_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction", "aMFSetRef"))
    assert (ref, RDF.type, OWL.ObjectProperty) in g
    assert (ref, Y2R.isReference, Literal(True)) in g
    assert list(g.objects(ref, RDFS.range)) == []


def test_typedef_is_datatype_not_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    dn = URIRef(cls_iri("_3gpp-common-yang-types", "DistinguishedName"))
    assert (dn, RDF.type, RDFS.Datatype) in g
    assert (dn, RDF.type, RDFS.Class) not in g


def test_invariant_leaf_annotated(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    # ausfInfo uses AusfInfoGrp, so its class is AusfInfo.
    prop = URIRef(prop_iri("_3gpp-5gc-nrm-ausffunction", "AusfInfo", "nFSrvGroupId"))
    assert (prop, Y2R.isInvariant, Literal(True)) in g


# --- properties of the new IRI scheme, over the whole real graph ---------

def test_property_local_name_is_class_scoped_with_a_dot(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    prop = URIRef(prop_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction", "aMFSetRef"))
    assert str(prop).endswith("#AMFFunction.aMFSetRef")
    assert (prop, RDFS.domain, AMF) in g


def test_property_label_matches_its_local_name(yang_dir, external_yams_dir):
    """The '.' scope separator was already this project's rdfs:label convention,
    so for an unqualified class the local name and the label now coincide."""
    g = _graph(yang_dir, external_yams_dir)
    prop = URIRef(prop_iri("_3gpp-5gc-nrm-ausffunction", "AusfInfo", "nFSrvGroupId"))
    assert (prop, RDFS.label, Literal("AusfInfo.nFSrvGroupId")) in g


def test_no_3gpp_org_iri_is_emitted(yang_dir, external_yams_dir):
    """3gpp.org is not ours to mint under; nothing may reference it."""
    g = _graph(yang_dir, external_yams_dir)
    bad = {str(x) for t in g for x in t
           if isinstance(x, URIRef) and "3gpp.org" in str(x)}
    assert not bad, f"{len(bad)} distinct 3gpp.org IRIs remain: {sorted(bad)[:3]}"


def test_no_urn_iri_is_emitted_in_the_tbox(yang_dir, external_yams_dir):
    """The base TBox carries no URNs at all; provenance lives in stamp_versions."""
    g = _graph(yang_dir, external_yams_dir)
    all_uris = {str(x) for t in g for x in t if isinstance(x, URIRef)}
    urns = {u for u in all_uris if u.startswith("urn:")}
    assert not urns, f"{len(urns)} of {len(all_uris)} distinct IRIs are still URNs"
