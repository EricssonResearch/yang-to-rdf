"""Split a merged RDF graph into per-module graphs for browsable output."""
from __future__ import annotations

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF

MODULE_URN_PREFIX = "urn:3gpp:sa5:"
# Aggregating ontology IRI used by index.ttl to owl:imports every module.
INDEX_ONTOLOGY = URIRef("https://3gpp.org/nrm/ontology")


def module_urn(iri) -> str | None:
    """Return the module-namespace URN for a class/property IRI, else None."""
    if not isinstance(iri, URIRef):
        return None
    s = str(iri)
    if not s.startswith(MODULE_URN_PREFIX):
        return None
    return s.split("/", 1)[0]


def module_stem(urn: str) -> str:
    """Filename stem for a module URN (matches the source .yang basename)."""
    return urn.rsplit(":", 1)[-1]


def split_graph(g: Graph) -> tuple[dict[str, Graph], Graph]:
    """Partition g into {module_urn: Graph} + a leftover index Graph.

    A triple is assigned to the module of its **subject** (when the subject is a
    module class/property IRI). Blank-node subgraphs (e.g. SHACL property shapes,
    rdf:List for sh:in) travel with the module URIRef that owns them, via the
    Concise Bounded Description (CBD) of that URIRef. Every other triple
    (nrm: vocab, stray subjects) goes to the leftover index graph. No triple is
    dropped: a final completeness pass routes anything not yet emitted to index.
    """
    modules: dict[str, Graph] = {}
    index = Graph()

    def _new_graph() -> Graph:
        ng = Graph()
        for prefix, ns in g.namespaces():
            ng.bind(prefix, ns)
        return ng

    emitted: set = set()
    # Seed only from URIRef subjects; CBD pulls their blank-node closure.
    for s in sorted((s for s in set(g.subjects()) if isinstance(s, URIRef)), key=str):
        urn = module_urn(s)
        target = modules.setdefault(urn, _new_graph()) if urn else index
        for t in g.cbd(s):
            target.add(t)
            emitted.add(t)

    # Completeness: any triple not captured above (orphan bnode subjects, etc.)
    for t in g:
        if t not in emitted:
            index.add(t)

    # Declare each module as an owl:Ontology and have the index import them.
    idx_onto = index
    idx_onto.add((INDEX_ONTOLOGY, RDF.type, OWL.Ontology))
    for urn, mg in modules.items():
        mg.add((URIRef(urn), RDF.type, OWL.Ontology))
        idx_onto.add((INDEX_ONTOLOGY, OWL.imports, URIRef(urn)))

    return modules, index
