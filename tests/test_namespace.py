"""The IRI scheme and its validation.

Scheme: docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md §4.
NCName is the production from XML Namespaces (W3C Recommendation, 8 Dec 2009);
the YANG identifier grammar is RFC 7950 §6.2.
"""
import pytest
from rdflib import Graph

from yang_to_rdf.namespace import (
    DEFAULT_BASE_IRI,
    NCNAME_RE,
    SCOPE_SEPARATOR,
    aggregate_ontology_iri,
    bind_standard_namespaces,
    class_iri,
    module_iri,
    module_stem,
    namespace_base,
    normalize_base_iri,
    property_iri,
    shape_iri,
    shapes_module_iri,
    version_iri,
    vocab_namespace,
)

BASE = DEFAULT_BASE_IRI
MOD = "_3gpp-5gc-nrm-amffunction"


def test_default_base_is_the_proposed_scheme():
    assert DEFAULT_BASE_IRI == "https://semantics.ericsson.com/"


def test_scope_separator_is_a_single_dot():
    assert SCOPE_SEPARATOR == "."


def test_module_and_term_iris():
    m = module_iri(BASE, MOD)
    assert m == "https://semantics.ericsson.com/yang/_3gpp-5gc-nrm-amffunction"
    nb = namespace_base(m)
    assert nb == m + "#"
    assert class_iri(nb, "AMFFunction") == m + "#AMFFunction"
    assert property_iri(nb, "AMFFunction", "pLMNId") == m + "#AMFFunction.pLMNId"


def test_shapes_live_in_a_separate_namespace():
    """A class named FooShape must not collide with the shape of Foo (spec §4)."""
    nb = namespace_base(module_iri(BASE, MOD))
    sb = namespace_base(shapes_module_iri(BASE, MOD))
    assert class_iri(nb, "FooShape") != shape_iri(sb, "Foo")


def test_vocab_aggregate_and_version_iris():
    assert str(vocab_namespace(BASE)) == "https://semantics.ericsson.com/vocab#"
    assert str(vocab_namespace(BASE).nameContains) == \
        "https://semantics.ericsson.com/vocab#nameContains"
    assert aggregate_ontology_iri(BASE) == "https://semantics.ericsson.com/ontology"
    assert version_iri(BASE, "Rel-19") == \
        "https://semantics.ericsson.com/ontology/version/Rel-19"


def test_version_label_is_percent_encoded_because_it_is_a_path_segment():
    """Release labels are user-supplied path segments, not NCNames (spec §5)."""
    assert version_iri(BASE, "Rel 19/x") == \
        "https://semantics.ericsson.com/ontology/version/Rel%2019%2Fx"


def test_module_stem_round_trips():
    assert module_stem(module_iri(BASE, MOD)) == MOD
    assert module_stem(shapes_module_iri(BASE, MOD)) == MOD


@pytest.mark.parametrize("base,expected", [
    ("https://example.org/x", "https://example.org/x/"),
    ("https://example.org/x/", "https://example.org/x/"),
    ("http://example.org/", "http://example.org/"),
])
def test_normalize_base_iri_adds_one_trailing_slash(base, expected):
    assert normalize_base_iri(base) == expected


@pytest.mark.parametrize("bad", [
    "yang/rel19",                 # relative
    "urn:3gpp:sa5:x",             # not http(s)
    "ftp://example.org/",         # wrong scheme
    "https:///nohost",            # empty authority
    "",
])
def test_normalize_base_iri_refuses_non_http_bases(bad):
    with pytest.raises(ValueError, match="RFC 3986"):
        normalize_base_iri(bad)


# --- G5: YANG identifier validation --------------------------------------
# Cannot be reached by real 3GPP YANG (all 2,014 local names are alphanumeric),
# so it is exercised only by these constructed inputs.

@pytest.mark.parametrize("bad", ["1leading", "-leading", ".leading", "has space",
                                 "has/slash", "has:colon", ""])
def test_class_iri_refuses_non_yang_identifiers(bad):
    with pytest.raises(ValueError, match="RFC 7950"):
        class_iri(namespace_base(module_iri(BASE, MOD)), bad)


# --- G9: the '.' separator must stay unambiguous -------------------------
# Also unreachable on the real corpus: 0 of 1,482 local names contain a dot.

def test_class_name_containing_the_separator_is_refused():
    nb = namespace_base(module_iri(BASE, MOD))
    with pytest.raises(ValueError, match=r"separator"):
        class_iri(nb, "Foo.Bar")


def test_property_name_containing_the_separator_is_refused():
    nb = namespace_base(module_iri(BASE, MOD))
    with pytest.raises(ValueError, match=r"separator"):
        property_iri(nb, "Foo", "bar.baz")


def test_separator_rejection_is_what_prevents_ambiguity():
    """Without G9, class 'A.B' and property 'B' of class 'A' would produce the
    same IRI. Documents the collision the guard exists to prevent."""
    nb = namespace_base(module_iri(BASE, MOD))
    # The collision that would occur if 'A.B' were allowed as a class name:
    assert property_iri(nb, "A", "B") == nb + "A.B"
    with pytest.raises(ValueError):
        class_iri(nb, "A.B")


def test_module_name_may_contain_a_dot():
    """A module name is a PATH segment, before the '#', so a dot is unambiguous
    there. Refusing it would reject legitimate vendor modules (`acme.router`).
    The separator rule applies only to local names, after the '#'."""
    m = module_iri(BASE, "vendor.mod.v2")
    assert m == "https://semantics.ericsson.com/yang/vendor.mod.v2"
    assert class_iri(namespace_base(m), "Router") == m + "#Router"


def test_module_name_must_still_be_a_yang_identifier():
    for bad in ("1mod", "-mod", "mod/x", ""):
        with pytest.raises(ValueError, match="RFC 7950"):
            module_iri(BASE, bad)


# --- G8: NCName legality -------------------------------------------------

@pytest.mark.parametrize("ok", ["A", "_", "_3gpp", "a.b", "a-b", "a_b", "X1"])
def test_ncname_regex_accepts_legal_names(ok):
    assert NCNAME_RE.match(ok)


@pytest.mark.parametrize("bad", ["1a", "-a", ".a", "a/b", "a:b", "a b", ""])
def test_ncname_regex_rejects_illegal_names(bad):
    assert not NCNAME_RE.match(bad)


def test_every_emitted_local_name_is_an_ncname():
    """The composed property local name must itself be a legal NCName -- the
    property this whole scheme exists to satisfy."""
    nb = namespace_base(module_iri(BASE, MOD))
    local = property_iri(nb, "AMFFunction", "pLMNId").rsplit("#", 1)[1]
    assert local == "AMFFunction.pLMNId"
    assert NCNAME_RE.match(local)


def test_bound_prefixes_include_y2r_and_not_nrm():
    g = Graph()
    bind_standard_namespaces(g, BASE)
    bound = {p: str(n) for p, n in g.namespaces()}
    assert bound["y2r"] == "https://semantics.ericsson.com/vocab#"
    assert "nrm" not in bound
