"""Split a merged RDF graph into per-module graphs for browsable output."""
from __future__ import annotations

from urllib.parse import quote

from rdflib import BNode, Graph, Literal, URIRef
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
    def _new_graph() -> Graph:
        ng = Graph()
        for prefix, ns in g.namespaces():
            ng.bind(prefix, ns)
        return ng

    modules: dict[str, Graph] = {}
    index = _new_graph()  # inherit prefixes so index.ttl serializes with nrm:/rdfs: etc.

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


def stamp_versions(graph: Graph, model, release_label: str | None = None,
                   aggregate: bool = False) -> None:
    """Add OWL version metadata to a graph.

    For each module URN in model.revisions that has subjects in graph, adds
    owl:versionInfo to the module ontology node (the URN itself).

    If aggregate=True and release_label is given, also adds owl:versionIRI
    and owl:versionInfo to the INDEX_ONTOLOGY.

    Args:
        graph: The RDF graph to stamp.
        model: The Model with .revisions dict[urn, (date, cr_ref_or_None)].
        release_label: Optional release label (e.g. "Rel-19").
        aggregate: Whether this is an aggregate ontology graph (for versionIRI).
    """
    # Find which module URNs have subjects present in this graph
    present_urns = set()
    for s in graph.subjects():
        if isinstance(s, URIRef):
            urn = module_urn(s)
            if urn:
                present_urns.add(urn)

    # Stamp module versionInfo for present modules (deterministic order)
    for urn in sorted(model.revisions):
        if urn not in present_urns:
            continue
        date, cr_ref = model.revisions[urn]
        version_string = f"revision {date}"
        if cr_ref:
            version_string += f" ({cr_ref})"

        graph.add((URIRef(urn), RDF.type, OWL.Ontology))
        graph.add((URIRef(urn), OWL.versionInfo, Literal(version_string)))

    # Stamp aggregate versionIRI if requested
    if aggregate and release_label:
        version_iri = URIRef(f"https://3gpp.org/nrm/ontology/version/{quote(release_label, safe='')}")
        graph.add((INDEX_ONTOLOGY, RDF.type, OWL.Ontology))
        graph.add((INDEX_ONTOLOGY, OWL.versionIRI, version_iri))
        graph.add((INDEX_ONTOLOGY, OWL.versionInfo, Literal(release_label)))
