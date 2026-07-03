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
    # thresholdInfoList is a MULTIVALUED nested dataType under ThresholdMonitor.attributes
    tm = next(c for c in model.iocs if c.name == "ThresholdMonitor")
    ref = next(a for a in tm.attr_refs if a.name == "thresholdInfoList")
    # its target is a datatype class carrying the structured leaves
    dt = next(c for c in model.classes if c.kind == "datatype"
              and c.name == "thresholdInfoList")
    assert "thresholdValue" in {l.name for l in dt.leaves}

def test_singleton_datatype_also_a_class(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    ausf = next(c for c in model.iocs if c.name == "AUSFFunction")
    ref = next(a for a in ausf.attr_refs if a.name == "ausfInfo")
    dt = next(c for c in model.classes if c.kind == "datatype" and c.name == "ausfInfo")
    inv = next(l for l in dt.leaves if l.name == "nFSrvGroupId")
    assert inv.is_invariant is True

def test_managed_element_contains_amffunction(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    me = next(c for c in model.iocs if c.name == "ManagedElement")
    assert any("AMFFunction" in c for c in me.contains)
