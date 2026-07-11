"""Split a merged RDF graph into per-module graphs for browsable output."""
from __future__ import annotations

from urllib.parse import quote

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF

# Aggregating ontology IRI used by index.ttl to owl:imports every module.
INDEX_ONTOLOGY = URIRef("https://3gpp.org/nrm/ontology")


def module_ns(iri, namespaces: set[str]) -> str | None:
    """Return the source-module namespace an IRI belongs to, else None.

    An emitted IRI is `<module-namespace>/Class[/prop]`, so it belongs to the
    (unique) namespace in `namespaces` that it starts with. Driven by the actual
    set of module namespaces the parser saw — scheme-agnostic, so non-3GPP or
    non-URN modules partition correctly too.
    """
    if not isinstance(iri, URIRef):
        return None
    s = str(iri)
    # Longest match wins in the unlikely case one namespace prefixes another.
    best = None
    for ns in namespaces:
        if s == ns or s.startswith(ns + "/"):
            if best is None or len(ns) > len(best):
                best = ns
    return best


def module_stem(ns: str) -> str:
    """Filename stem for a module namespace (matches the source .yang basename).

    e.g. `urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction` -> `_3gpp-5gc-nrm-amffunction`.
    """
    return ns.rsplit(":", 1)[-1].rsplit("/", 1)[-1]


def split_graph(g: Graph, namespaces: set[str]) -> tuple[dict[str, Graph], Graph]:
    """Partition g into {module_namespace: Graph} + a leftover index Graph.

    A triple is assigned to the module of its **subject** (when the subject IRI
    belongs to one of `namespaces`, the parser's set of source-module
    namespaces). Blank-node subgraphs (e.g. SHACL property shapes, the rdf:List
    behind sh:in) travel with the module IRI that owns them, via its Concise
    Bounded Description — CBD = the subject's triples plus, transitively, every
    blank node reachable from them (rdflib's Graph.cbd). Every other triple
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
        ns = module_ns(s, namespaces)
        target = modules.setdefault(ns, _new_graph()) if ns else index
        for t in g.cbd(s):
            target.add(t)
            emitted.add(t)

    # Completeness: any triple not captured above (orphan bnode subjects, etc.)
    for t in g:
        if t not in emitted:
            index.add(t)

    # Declare each module as an owl:Ontology and have the index import them.
    index.add((INDEX_ONTOLOGY, RDF.type, OWL.Ontology))
    for ns in modules:
        modules[ns].add((URIRef(ns), RDF.type, OWL.Ontology))
        index.add((INDEX_ONTOLOGY, OWL.imports, URIRef(ns)))

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
    # Which module namespaces have subjects present in this graph? We only stamp
    # modules that carry a revision, so the revision keys are the candidate set
    # (they are module namespaces); union module_namespaces for completeness.
    candidates = set(model.revisions) | set(model.module_namespaces)
    present = set()
    for s in graph.subjects():
        if isinstance(s, URIRef):
            ns = module_ns(s, candidates)
            if ns:
                present.add(ns)

    # Stamp module versionInfo for present modules (deterministic order)
    for ns in sorted(model.revisions):
        if ns not in present:
            continue
        date, cr_ref = model.revisions[ns]
        version_string = f"revision {date}"
        if cr_ref:
            version_string += f" ({cr_ref})"

        graph.add((URIRef(ns), RDF.type, OWL.Ontology))
        graph.add((URIRef(ns), OWL.versionInfo, Literal(version_string)))

    # Stamp aggregate versionIRI if requested
    if aggregate and release_label:
        version_iri = URIRef(f"https://3gpp.org/nrm/ontology/version/{quote(release_label, safe='')}")
        graph.add((INDEX_ONTOLOGY, RDF.type, OWL.Ontology))
        graph.add((INDEX_ONTOLOGY, OWL.versionIRI, version_iri))
        graph.add((INDEX_ONTOLOGY, OWL.versionInfo, Literal(release_label)))
