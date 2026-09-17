"""Cached, read-only build of the model/graphs so the slow YANG parse runs once
per test session instead of once per test. Tests treat these as immutable."""
import glob
import os
from functools import lru_cache

from yang_to_rdf.pyang_context import build_context
from yang_to_rdf.yang_parser import parse
from yang_to_rdf.rdf_converter import YangToRDFConverter
from yang_to_rdf.shacl_converter import YangToSHACLConverter
from yang_to_rdf.reference_layer import ReferenceLayerBuilder


@lru_cache(maxsize=None)
def cached_context(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    return build_context(files, [yang_dir, external_yams_dir])


@lru_cache(maxsize=None)
def cached_parse(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    return parse(files, [yang_dir, external_yams_dir])


@lru_cache(maxsize=None)
def cached_rdf_graph(yang_dir, external_yams_dir):
    model, _ = cached_parse(yang_dir, external_yams_dir)
    return YangToRDFConverter(model).convert()


@lru_cache(maxsize=None)
def cached_shacl_graph(yang_dir, external_yams_dir):
    model, _ = cached_parse(yang_dir, external_yams_dir)
    return YangToSHACLConverter(model).convert()


@lru_cache(maxsize=None)
def cached_refs_graph(yang_dir, external_yams_dir):
    model, _ = cached_parse(yang_dir, external_yams_dir)
    return ReferenceLayerBuilder(model).build()


# --- IRI derivation for tests -------------------------------------------
# Tests must never retype an IRI literal: a retyped literal is a copy of a value
# the code owns, and copies drift. Everything below composes IRIs through the
# same helpers the converters use, so a scheme change cannot leave a stale
# expectation asserting the old shape was correct.

from yang_to_rdf.namespace import (  # noqa: E402
    DEFAULT_BASE_IRI,
    class_iri,
    module_iri,
    namespace_base,
    property_iri,
    shape_iri,
    shapes_module_iri,
    vocab_namespace,
)

BASE = DEFAULT_BASE_IRI
Y2R = vocab_namespace(BASE)


def mod_iri(module: str) -> str:
    """Module ontology IRI for a declared YANG module name."""
    return module_iri(BASE, module)


def cls_iri(module: str, name: str) -> str:
    """Class / typedef IRI: <base>yang/<module>#<name>."""
    return class_iri(namespace_base(mod_iri(module)), name)


def prop_iri(module: str, cls: str, prop: str) -> str:
    """Property IRI: <base>yang/<module>#<Class>.<prop>."""
    return property_iri(namespace_base(mod_iri(module)), cls, prop)


def shp_iri(module: str, cls: str) -> str:
    """SHACL NodeShape IRI: <base>shapes/<module>#<Class>."""
    return shape_iri(namespace_base(shapes_module_iri(BASE, module)), cls)
