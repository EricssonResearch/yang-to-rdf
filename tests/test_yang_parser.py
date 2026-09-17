# tests/test_yang_parser.py
from tests._shared import cached_parse as _model

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
    assert "userLabel" in {lf.name for lf in amf.leaves}

def test_dn_reference_leaf_flagged(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    amf = next(c for c in model.iocs if c.name == "AMFFunction")
    ref = next(lf for lf in amf.leaves if lf.name == "aMFSetRef")
    assert ref.is_reference is True

def test_datatype_modeled_as_class_not_dropped(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    # thresholdInfoList uses ThresholdInfoGrp, so its class is now ThresholdInfo
    tm = next(c for c in model.iocs if c.name == "ThresholdMonitor")
    next(a for a in tm.attr_refs if a.name == "thresholdInfoList")  # must exist
    # its target is a datatype class carrying the structured leaves
    dt = next(c for c in model.classes if c.kind == "datatype"
              and c.name == "ThresholdInfo")
    assert "thresholdValue" in {lf.name for lf in dt.leaves}

def test_singleton_datatype_also_a_class(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    ausf = next(c for c in model.iocs if c.name == "AUSFFunction")
    next(a for a in ausf.attr_refs if a.name == "ausfInfo")  # must exist
    # ausfInfo uses AusfInfoGrp, so its class is now AusfInfo
    dt = next(c for c in model.classes if c.kind == "datatype" and c.name == "AusfInfo")
    inv = next(lf for lf in dt.leaves if lf.name == "nFSrvGroupId")
    assert inv.is_invariant is True

def test_managed_element_contains_amffunction(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    me = next(c for c in model.iocs if c.name == "ManagedElement")
    assert any("AMFFunction" in c for c in me.contains)

def test_choice_case_leaves_flattened(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    pmj = next(c for c in model.iocs if c.name == "PerfMetricJob")
    names = {lf.name for lf in pmj.leaves}
    # streamTarget lives inside a choice/case under PerfMetricJob.attributes
    assert "streamTarget" in names
    assert "fileReportingPeriod" in names

def test_nested_container_leaves_flattened(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    nrc = next(c for c in model.iocs if c.name == "NRCellRelation")
    # cellIndividualOffset is a nested container; its leaves flatten onto NRCellRelation
    assert "rsrpOffsetSsb" in {lf.name for lf in nrc.leaves}

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
    assert ref.target_iri.endswith("#ServiceProfile")
    sp = next(c for c in model.classes if c.name == "ServiceProfile")
    assert "availability" in {lf.name for lf in sp.leaves}

def test_shared_grouping_is_single_class(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    geoareas = [c for c in model.classes if c.name == "GeoArea"]
    assert len(geoareas) == 1, f"expected one shared GeoArea, got {len(geoareas)}"
    # multiple properties across the model point their range at it
    ga_iri_end = "#GeoArea"
    users = [a for c in model.classes for a in c.attr_refs
             if a.target_iri.endswith(ga_iri_end)]
    assert len(users) >= 3


# --- module identity under the HTTP IRI scheme ---------------------------
# Spec: docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md §4, D2/D6.

from yang_to_rdf.namespace import DEFAULT_BASE_IRI, module_iri  # noqa: E402


def test_module_identity_is_the_declared_module_name(parsed_model):
    """Keying on the module name, not the YANG namespace, corrects two real
    upstream discrepancies (spec §4). Both are asserted, not assumed."""
    model, _ = parsed_model
    typo = module_iri(DEFAULT_BASE_IRI, "_3gpp-5gc-nrm-externalseppfunction")
    sector = module_iri(DEFAULT_BASE_IRI, "_3gpp-nr-nrm-nrsectorcarrier")
    assert typo in model.module_iris, "module name should win over the typo'd namespace"
    assert sector in model.module_iris
    assert not any("extternal" in m for m in model.module_iris)
    assert not any("nrnetwork-nrsectorcarrier" in m for m in model.module_iris)


def test_yang_namespace_urns_are_retained_as_provenance(parsed_model):
    model, _ = parsed_model
    assert len(model.module_yang_namespace) == len(model.module_iris), (
        f"{len(model.module_yang_namespace)} provenance entries for "
        f"{len(model.module_iris)} modules")
    typo = module_iri(DEFAULT_BASE_IRI, "_3gpp-5gc-nrm-externalseppfunction")
    assert model.module_yang_namespace[typo] == \
        "urn:3gpp:sa5:_3gpp-5gc-nrm-extternalseppfunction"


def test_no_urn_survives_in_class_or_typedef_namespaces(parsed_model):
    model, _ = parsed_model
    bad = [c.namespace for c in model.classes if c.namespace.startswith("urn:")]
    bad += [t.namespace for t in model.typedefs if t.namespace.startswith("urn:")]
    total = len(model.classes) + len(model.typedefs)
    assert not bad, f"{len(bad)} of {total} terms kept a URN namespace"


def test_every_class_namespace_is_a_known_module_iri(parsed_model):
    model, _ = parsed_model
    seen = {c.namespace for c in model.classes} | {t.namespace for t in model.typedefs}
    unknown = seen - model.module_iris
    assert not unknown, (
        f"{len(unknown)} of {len(seen)} term namespaces are not module IRIs: "
        f"{sorted(unknown)[:3]}")


def test_submodule_classes_resolve_to_their_parent_module(parsed_model):
    """The 2 submodules in this set declare no `namespace`; their groupings must
    resolve through `belongs-to` (RFC 7950 §7.2.2) to the parent module."""
    model, _ = parsed_model
    names = {c.name: c.namespace for c in model.classes}
    assert names["ServiceProfile"] == module_iri(
        DEFAULT_BASE_IRI, "_3gpp-ns-nrm-networkslice")
    assert names["SliceProfile"] == module_iri(
        DEFAULT_BASE_IRI, "_3gpp-ns-nrm-networkslicesubnet")


def test_base_iri_is_threaded_through_parse(yang_dir, external_yams_dir):
    import glob
    import os

    from yang_to_rdf.yang_parser import parse
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp-common-top.yang")))
    assert files, "fixture module not found -- the check could not run"
    model, _ = parse(files, [yang_dir, external_yams_dir],
                     base_iri="https://example.org/x/")
    assert model.base_iri == "https://example.org/x/"
    assert model.module_iris, "no modules registered"
    assert all(m.startswith("https://example.org/x/yang/") for m in model.module_iris)
