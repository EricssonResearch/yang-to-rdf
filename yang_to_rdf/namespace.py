"""IRI construction and shared graph setup for the RDF converters.

Strategy:
- A module's YANG namespace (e.g. urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction) is the base.
- Class IRI: <base>/ClassName
- Property IRI: <base>/ClassName/propertyName  (path-scoped, avoids multi-domain
  collisions when the same local name appears on several classes).
"""

from __future__ import annotations

from urllib.parse import quote

from rdflib import Graph, Namespace
from rdflib.namespace import OWL, RDF, RDFS, XSD

# 3GPP NRM project vocabulary (the tool's only non-standard namespace).
NRM = Namespace("https://3gpp.org/nrm/vocab#")


def namespace_base(namespace: str) -> str:
    """The IRI base for a module namespace: the namespace plus a trailing '/'."""
    return namespace + "/"


def class_iri(base: str, class_name: str) -> str:
    """Build IRI for a class (IOC)."""
    return f"{base}{quote(class_name, safe='')}"


def property_iri(base: str, class_name: str, prop_name: str) -> str:
    """Build path-scoped property IRI: <base>/ClassName/propName."""
    return f"{base}{quote(class_name, safe='')}/{quote(prop_name, safe='')}"


def bind_standard_namespaces(graph: Graph) -> None:
    """Bind the prefixes every converter uses, so serialized TTL is readable."""
    for prefix, ns in (("rdf", RDF), ("rdfs", RDFS), ("owl", OWL),
                       ("xsd", XSD), ("nrm", NRM)):
        graph.bind(prefix, ns)
