"""IRI construction and shared graph setup for the RDF converters.

Scheme (docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md §4)::

    <base>vocab#<term>                    minted vocabulary        prefix y2r:
    <base>ontology                        aggregate ontology
    <base>ontology/version/<label>        owl:versionIRI
    <base>yang/<module>                   per-module ontology
    <base>yang/<module>#<Class>           class / typedef
    <base>yang/<module>#<Class>.<prop>    property, class-scoped
    <base>shapes/<module>#<Class>         SHACL NodeShape

Each module gets a *hash namespace* so that every local name is a legal NCName
(XML Namespaces, W3C Recommendation 8 Dec 2009) and so that a module's terms all
share one namespace -- which the two-level slash form this replaces did not
achieve: properties sat in a namespace per class, so no prefix bound them.

Hash over slash follows the size criterion in "Best Practice Recipes for
Publishing RDF Vocabularies" (W3C *Working Group Note*, 28 Aug 2008 -- guidance,
not a Recommendation, and it says so of itself). A median of 70 terms and at most
256 per module puts this in its "single Web access" case, so serving the
vocabulary later needs only static files: no 303 redirects, no content
negotiation.

The default base names an Ericsson-owned namespace that is NOT currently
dereferenceable (semantics.ericsson.com had no DNS record as of 2026-09-17).
Terms under it are minted by this project and assert no 3GPP endorsement.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

from rdflib import Graph, Namespace
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, XSD

# Ericsson-owned, ours, not currently dereferenceable. See the module docstring.
DEFAULT_BASE_IRI = "https://semantics.ericsson.com/"

# Joins a class and property local name: <Class>.<prop>. OURS -- no standard
# prescribes it. It is legal in a non-initial NCName position, and it is already
# this project's convention for rdfs:label (every property label is
# "<Class>.<prop>").
#
# No ASCII separator is free of a THEORETICAL ambiguity, because RFC 7950
# identifiers and NCNames permit the same character set: a class named `A.B`
# would produce the same local name as property `B` of class `A`. An earlier
# draft refused every identifier containing '.', which was wrong -- the IETF
# `ietf-yang-types` module that nearly every 3GPP module imports defines
# `typedef xpath1.0` (RFC 6991), so refusing dots breaks the primary use case.
#
# The ambiguity is much narrower than "contains a dot". A split is only a real
# alternative reading if BOTH halves are legal YANG identifiers, and an
# identifier cannot begin with a digit -- so `xpath1.0` has no valid split and
# is unambiguously one name. is_ambiguous_local_name() below decides this
# precisely, and gate G2 asserts it over the whole corpus (measured: 0 ambiguous
# of 7,225 local names). See spec §3.
SCOPE_SEPARATOR = "."

# NCName restricted to the ASCII range, which is all an RFC 7950 identifier can
# contain. XML Namespaces defines NCName as an XML Name minus ':', so '/' is
# excluded by construction and the first character cannot be a digit, '-' or '.'.
NCNAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*\Z")

# RFC 7950 §6.2: identifier = (ALPHA / "_") *(ALPHA / DIGIT / "_" / "-" / ".")
YANG_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*\Z")


def normalize_base_iri(base: str) -> str:
    """Validate a base IRI and guarantee exactly one trailing '/'."""
    parts = urlsplit(base or "")
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(
            f"--base-iri must be an absolute http(s) IRI with an authority "
            f"(RFC 3986 §3): got {base!r}"
        )
    return base if base.endswith("/") else base + "/"


def _check_yang_identifier(name: str, what: str) -> str:
    """Refuse anything that is not a YANG identifier.

    Applies to module names, which become a *path segment*. A '.' is
    unambiguous there, so the separator rule below does not apply -- refusing it
    would reject legitimate vendor module names like `acme.router`.
    """
    if not YANG_IDENTIFIER_RE.match(name or ""):
        raise ValueError(
            f"{what} {name!r} is not a valid YANG identifier (RFC 7950 §6.2), "
            f"so it cannot form a legal NCName local part "
            f"(XML Namespaces, W3C Recommendation)"
        )
    return name


def _check_local_name(name: str, what: str) -> str:
    """Validate a class or property name destined for an NCName local part.

    Identical to _check_yang_identifier today; kept as a distinct seam because
    local names carry the extra obligation of composing unambiguously, which is
    enforced corpus-wide by is_ambiguous_local_name / gate G2 rather than by
    rejecting individual names. See the SCOPE_SEPARATOR comment.
    """
    return _check_yang_identifier(name, what)


def split_local_name(local: str) -> list[tuple[str, str]]:
    """Every reading of a composed local name as (class, property).

    A split at SCOPE_SEPARATOR is only a real alternative reading when BOTH
    halves are legal YANG identifiers. Since an identifier cannot start with a
    digit, `xpath1.0` yields no splits and is unambiguously a single name, while
    `AMFFunction.pLMNId` yields exactly one.
    """
    out = []
    for i, ch in enumerate(local):
        if ch != SCOPE_SEPARATOR:
            continue
        head, tail = local[:i], local[i + 1:]
        if YANG_IDENTIFIER_RE.match(head) and YANG_IDENTIFIER_RE.match(tail):
            out.append((head, tail))
    return out


def is_ambiguous_local_name(local: str) -> bool:
    """True when a local name could be read as more than one term.

    Ambiguity needs two or more valid (class, property) splits, or one valid
    split for a name that is *also* a legal standalone identifier -- the case
    where a class named `A.B` collides with property `B` of class `A`. Callers
    resolve which of those actually occur; this only reports the possibility.
    """
    return len(split_local_name(local)) > 1


def vocab_namespace(base: str) -> Namespace:
    """The project's minted vocabulary. The entire non-standard term surface."""
    return Namespace(f"{base}vocab#")


def aggregate_ontology_iri(base: str) -> str:
    """The ontology that owl:imports every module (carried by index.ttl)."""
    return f"{base}ontology"


def version_iri(base: str, label: str) -> str:
    """owl:versionIRI for a release label.

    The label is a user-supplied *path segment*, not an NCName, so
    percent-encoding is correct here -- unlike term local names, which are
    validated and refused instead.
    """
    return f"{base}ontology/version/{quote(label, safe='')}"


def module_iri(base: str, module_name: str) -> str:
    """Per-module ontology IRI, keyed on the declared YANG module name."""
    return f"{base}yang/{_check_yang_identifier(module_name, 'module name')}"


def shapes_module_iri(base: str, module_name: str) -> str:
    """Shapes-document IRI for a module.

    Separate from the class namespace so a YANG class genuinely named `FooShape`
    cannot collide with the SHACL shape of `Foo`. Structural, rather than relying
    on no such class existing.
    """
    return f"{base}shapes/{_check_yang_identifier(module_name, 'module name')}"


def namespace_base(module_iri_: str) -> str:
    """The hash namespace for a module (or shapes) ontology IRI."""
    return module_iri_ + "#"


def class_iri(base: str, class_name: str) -> str:
    """Build IRI for a class (IOC or dataType) or a typedef."""
    return f"{base}{_check_local_name(class_name, 'class name')}"


def property_iri(base: str, class_name: str, prop_name: str) -> str:
    """Build a class-scoped property IRI: <base>#<Class>.<prop>.

    Class-scoped because property local names are heavily reused across classes
    within one module, so a flat namespace would merge distinct properties.
    """
    return (f"{base}{_check_local_name(class_name, 'class name')}"
            f"{SCOPE_SEPARATOR}{_check_local_name(prop_name, 'property name')}")


def shape_iri(shapes_base: str, class_name: str) -> str:
    """Build a SHACL NodeShape IRI in the module's shapes namespace."""
    return f"{shapes_base}{_check_local_name(class_name, 'class name')}"


def module_stem(module_iri_: str) -> str:
    """Filename stem for a module IRI: the declared YANG module name.

    e.g. `https://semantics.ericsson.com/yang/_3gpp-5gc-nrm-amffunction`
    -> `_3gpp-5gc-nrm-amffunction`.
    """
    return module_iri_.rsplit("/", 1)[-1]


def bind_standard_namespaces(graph: Graph, base: str) -> None:
    """Bind the prefixes every converter uses, so serialized TTL is readable."""
    for prefix, ns in (("rdf", RDF), ("rdfs", RDFS), ("owl", OWL),
                       ("xsd", XSD), ("y2r", vocab_namespace(base)),
                       ("dcterms", DCTERMS)):
        graph.bind(prefix, ns)
