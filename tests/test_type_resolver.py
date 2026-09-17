# tests/test_type_resolver.py
from yang_to_rdf.type_resolver import resolve_type
from rdflib.namespace import XSD
from tests._shared import cached_context

def _ctx(yang_dir, external_yams_dir):
    return cached_context(yang_dir, external_yams_dir)[0]

def _find_leaf(ctx, module, leaf_name):
    m = ctx.get_module(module)
    stack = list(m.substmts)
    while stack:
        c = stack.pop()
        stack += list(c.substmts)
        if c.keyword in ("leaf", "leaf-list") and c.arg == leaf_name:
            return c
    raise AssertionError(f"leaf {leaf_name} not found")

def test_dn_leaf_is_reference(yang_dir, external_yams_dir):
    ctx = _ctx(yang_dir, external_yams_dir)
    leaf = _find_leaf(ctx, "_3gpp-5gc-nrm-amffunction", "aMFSetRef")
    rt = resolve_type(leaf.search_one("type"))
    assert rt.is_reference is True
    assert rt.pattern is not None  # DN pattern carried through

def test_enum_typedef_resolves_enums(yang_dir, external_yams_dir):
    ctx = _ctx(yang_dir, external_yams_dir)
    # a leaf whose type is the CommModelType enum typedef
    m = ctx.get_module("_3gpp-5g-common-yang-types")
    td = m.search_one("typedef", "CommModelType")
    rt = resolve_type(td.search_one("type"))
    assert len(rt.enums) > 0

def test_plain_string_leaf(yang_dir, external_yams_dir):
    ctx = _ctx(yang_dir, external_yams_dir)
    leaf = _find_leaf(ctx, "_3gpp-common-managed-function", "userLabel")
    rt = resolve_type(leaf.search_one("type"))
    assert rt.xsd == XSD.string
    assert rt.is_reference is False
