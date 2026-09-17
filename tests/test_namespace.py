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
    is_ambiguous_local_name,
    module_iri,
    module_stem,
    namespace_base,
    normalize_base_iri,
    property_iri,
    shape_iri,
    shapes_module_iri,
    split_local_name,
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
# Cannot be reached by real 3GPP YANG: 0 of 7,225 local names in the Rel-19 set
# are non-NCName. So it is exercised only by these constructed inputs.

@pytest.mark.parametrize("bad", ["1leading", "-leading", ".leading", "has space",
                                 "has/slash", "has:colon", ""])
def test_class_iri_refuses_non_yang_identifiers(bad):
    with pytest.raises(ValueError, match="RFC 7950"):
        class_iri(namespace_base(module_iri(BASE, MOD)), bad)


# --- G9: composed local names must be unambiguous ------------------------
# NOT by refusing dots. The IETF ietf-yang-types module that nearly every 3GPP
# module imports defines `typedef xpath1.0` (RFC 6991), so a blanket refusal
# breaks the primary use case. Measured over the real corpus: 1 of 7,225 local
# names contains a dot, and 0 are ambiguous.

def test_a_dotted_typedef_name_from_ietf_yang_types_is_accepted():
    """Regression: an earlier draft refused this, breaking every 3GPP module."""
    nb = namespace_base(module_iri(BASE, "ietf-yang-types"))
    assert class_iri(nb, "xpath1.0").endswith("#xpath1.0")


def test_xpath1_0_has_no_valid_split_so_it_is_unambiguous():
    """A property named '0' is impossible -- YANG identifiers must start with a
    letter or '_' (RFC 7950 §6.2) -- so there is only one reading."""
    assert split_local_name("xpath1.0") == []
    assert not is_ambiguous_local_name("xpath1.0")


def test_a_normal_property_local_name_has_exactly_one_reading():
    assert split_local_name("AMFFunction.pLMNId") == [("AMFFunction", "pLMNId")]
    assert not is_ambiguous_local_name("AMFFunction.pLMNId")


def test_a_genuinely_ambiguous_local_name_is_detected():
    """Two valid splits: class 'A' prop 'B.C', or class 'A.B' prop 'C'. This is
    the collision the guard exists to catch. No such name exists in the 3GPP
    corpus (0 of 7,225), which is why it must be tested with constructed input."""
    assert split_local_name("A.B.C") == [("A", "B.C"), ("A.B", "C")]
    assert is_ambiguous_local_name("A.B.C")


def test_the_collision_that_ambiguity_would_cause():
    """Documents why it matters: two distinct terms, one IRI."""
    nb = namespace_base(module_iri(BASE, MOD))
    assert property_iri(nb, "A", "B.C") == property_iri(nb, "A.B", "C")


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
