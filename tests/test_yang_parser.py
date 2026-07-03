# tests/test_yang_parser.py
import glob, os
from yang_to_rdf.yang_parser import parse

def _model(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    return parse(files, [yang_dir, external_yams_dir])

def test_parses_cleanly(yang_dir, external_yams_dir):
    _, errors = _model(yang_dir, external_yams_dir)
    assert errors == []

def test_amffunction_is_ioc_subclass_managed_function(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    amf = next(c for c in model.iocs if c.name == "AMFFunction")
    assert amf.kind == "ioc"
    assert any("ManagedFunction" in s for s in amf.subclass_of)

def test_inherited_leaf_present(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    amf = next(c for c in model.iocs if c.name == "AMFFunction")
    assert "userLabel" in {l.name for l in amf.leaves}

def test_dn_reference_leaf_flagged(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    amf = next(c for c in model.iocs if c.name == "AMFFunction")
    ref = next(l for l in amf.leaves if l.name == "aMFSetRef")
    assert ref.is_reference is True

def test_datatype_modeled_as_class_not_dropped(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    # thresholdInfoList uses ThresholdInfoGrp, so its class is now ThresholdInfo
    tm = next(c for c in model.iocs if c.name == "ThresholdMonitor")
    ref = next(a for a in tm.attr_refs if a.name == "thresholdInfoList")
    # its target is a datatype class carrying the structured leaves
    dt = next(c for c in model.classes if c.kind == "datatype"
              and c.name == "ThresholdInfo")
    assert "thresholdValue" in {l.name for l in dt.leaves}

def test_singleton_datatype_also_a_class(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    ausf = next(c for c in model.iocs if c.name == "AUSFFunction")
    ref = next(a for a in ausf.attr_refs if a.name == "ausfInfo")
    # ausfInfo uses AusfInfoGrp, so its class is now AusfInfo
    dt = next(c for c in model.classes if c.kind == "datatype" and c.name == "AusfInfo")
    inv = next(l for l in dt.leaves if l.name == "nFSrvGroupId")
    assert inv.is_invariant is True

def test_managed_element_contains_amffunction(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    me = next(c for c in model.iocs if c.name == "ManagedElement")
    assert any("AMFFunction" in c for c in me.contains)

def test_choice_case_leaves_flattened(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    pmj = next(c for c in model.iocs if c.name == "PerfMetricJob")
    names = {l.name for l in pmj.leaves}
    # streamTarget lives inside a choice/case under PerfMetricJob.attributes
    assert "streamTarget" in names
    assert "fileReportingPeriod" in names

def test_nested_container_leaves_flattened(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    nrc = next(c for c in model.iocs if c.name == "NRCellRelation")
    # cellIndividualOffset is a nested container; its leaves flatten onto NRCellRelation
    assert "rsrpOffsetSsb" in {l.name for l in nrc.leaves}

def test_nested_ioc_not_misclassified_as_datatype(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    # dynamic5QIs has an attributes container everywhere it appears -> must be ioc
    kinds = {c.kind for c in model.classes if c.name == "dynamic5QIs"}
    assert kinds == {"ioc"}, f"dynamic5QIs kinds={kinds}"

def test_no_unmodeled_attribute_kinds(yang_dir, external_yams_dir):
    _, errors = _model(yang_dir, external_yams_dir)
    assert not any("unmodeled attribute node kind" in e for e in errors), errors

def test_serviceprofile_class_named_from_grouping(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    names = {c.name for c in model.classes}
    assert "ServiceProfile" in names
    assert "serviceProfileList" not in names   # collection name no longer a class
    ns = next(c for c in model.iocs if c.name == "NetworkSlice")
    ref = next(a for a in ns.attr_refs if a.name == "serviceProfileList")
    assert ref.target_iri.endswith("/ServiceProfile")
    sp = next(c for c in model.classes if c.name == "ServiceProfile")
    assert "availability" in {l.name for l in sp.leaves}

def test_shared_grouping_is_single_class(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    geoareas = [c for c in model.classes if c.name == "GeoArea"]
    assert len(geoareas) == 1, f"expected one shared GeoArea, got {len(geoareas)}"
    # multiple properties across the model point their range at it
    ga_iri_end = "/GeoArea"
    users = [a for c in model.classes for a in c.attr_refs
             if a.target_iri.endswith(ga_iri_end)]
    assert len(users) >= 3
