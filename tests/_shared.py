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
