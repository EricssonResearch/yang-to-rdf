"""Split a merged RDF graph into per-module graphs for browsable output."""
from __future__ import annotations

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

from yang_to_rdf.namespace import (
    NCNAME_RE,
    aggregate_ontology_iri,
    module_stem,
    namespace_base,
    shapes_module_iri,
    version_iri,
    vocab_namespace,
)

__all__ = [
    "bind_used_prefixes", "module_prefix_map", "module_ns", "module_stem",
    "split_graph", "stamp_versions", "turtle_prefixes",
]


def turtle_prefixes(model) -> dict[str, str]:
    """Turtle prefix -> namespace, using each module's OWN YANG `prefix`.

    YANG modules already declare a short, author-chosen prefix (RFC 7950 §7.1.4)
    — `amf3gpp`, `mf3gpp` — so there is no need to invent one, and the emitted
    Turtle reads like the source YANG. Measured on the 3GPP Rel-19 set: 118
    modules, 118 distinct prefixes, all NCName-legal, zero collisions.

    YANG only requires prefix uniqueness within a module's own import scope, not
    across an arbitrary module set, so collisions are resolved deterministically
    by appending -2, -3, ... in sorted module order. A module declaring no usable
    prefix falls back to its module name.
    """
    out: dict[str, str] = {}
    taken: set[str] = set()
    for mod in sorted(model.module_iris):
        meta = model.module_meta.get(mod)
        stem = module_stem(mod)
        wanted = meta.prefix if meta is not None and meta.prefix else stem
        if not NCNAME_RE.match(wanted):
            wanted = stem
        prefix, n = wanted, 2
        while prefix in taken:
            prefix, n = f"{wanted}-{n}", n + 1
        taken.add(prefix)
        out[prefix] = namespace_base(mod)
        out[f"{prefix}-shapes"] = namespace_base(
            shapes_module_iri(model.base_iri, stem))
    return out


def bind_used_prefixes(graph: Graph, prefixes: dict[str, str]) -> int:
    """Bind only the prefixes whose namespace actually appears in `graph`.

    Returns the number bound, so a caller can assert it did something.

    Binding ALL per-module prefixes on every graph is what a naive
    implementation does, and it cost a 10x slowdown on the Rel-19 set (354s vs
    35s): rdflib consults every binding for every term it serializes, so 214
    bindings copied into 286 graphs is quadratic-ish waste. A module file
    references only a handful of other modules, so scanning first and binding the
    subset is both faster and produces less prefix noise in the output.
    """
    seen: set[str] = set()
    for triple in graph:
        for term in triple:
            if isinstance(term, URIRef):
                s = str(term)
                cut = s.rfind("#")
                if cut != -1:
                    seen.add(s[:cut + 1])
    bound = 0
    for prefix, ns in prefixes.items():
        if ns in seen:
            graph.bind(prefix, Namespace(ns))
            bound += 1
    return bound


def _stamp_module_meta(graph: Graph, ns: str, model) -> None:
    """Add Dublin Core metadata to a module ontology node, sourced from the
    module's own YANG statements (organization/contact/description/reference).
    Each mapping is emitted only when the source statement was present."""
    meta = model.module_meta.get(ns)
    if meta is None:
        return
    node = URIRef(ns)
    # A title is required for ontology documentation tools (e.g. pyLODE); use the
    # module name, which is always present.
    graph.add((node, DCTERMS.title, Literal(meta.name)))
    graph.add((node, RDFS.label, Literal(meta.name)))
    if meta.description:
        graph.add((node, DCTERMS.description, Literal(meta.description)))
    if meta.organization:
        graph.add((node, DCTERMS.publisher, Literal(meta.organization)))
    if meta.contact:
        # 3GPP `contact` is typically a URL; expose it as a see-also link.
        graph.add((node, RDFS.seeAlso, Literal(meta.contact)))
    if meta.reference:
        graph.add((node, DCTERMS.source, Literal(meta.reference)))


def module_prefix_map(base: str, module_iris: set[str]) -> dict[str, str]:
    """IRI prefix -> owning module IRI.

    Each module contributes TWO prefixes: its own ontology IRI (classes,
    properties, typedefs) and its shapes ontology IRI. Both route to the same
    module so a module's three output files stay together, while shapes keep a
    namespace of their own — which is what makes a class named `FooShape` unable
    to collide with the shape of `Foo` (spec §4).
    """
    pmap: dict[str, str] = {}
    for m in module_iris:
        pmap[m] = m
        pmap[shapes_module_iri(base, module_stem(m))] = m
    return pmap


def module_ns(iri, prefix_map: dict[str, str]) -> str | None:
    """Return the module IRI an emitted IRI belongs to, else None.

    A term is `<prefix>#<local>`; the module ontology node is `<prefix>` exactly.
    Requiring the '#' for the term form is what stops `<base>yang/mod` from
    capturing `<base>yang/mod-extra#X`. Longest match wins as belt-and-braces.
    """
    if not isinstance(iri, URIRef):
        return None
    s = str(iri)
    best_prefix = None
    for prefix in prefix_map:
        if s == prefix or s.startswith(prefix + "#"):
            if best_prefix is None or len(prefix) > len(best_prefix):
                best_prefix = prefix
    return prefix_map[best_prefix] if best_prefix is not None else None


def split_graph(g: Graph, prefix_map: dict[str, str],
                base_iri: str) -> tuple[dict[str, Graph], Graph]:
    """Partition g into {module_iri: Graph} + a leftover index Graph.

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
        mod = module_ns(s, prefix_map)
        target = modules.setdefault(mod, _new_graph()) if mod else index
        for t in g.cbd(s):
            target.add(t)
            emitted.add(t)

    # Completeness: any triple not captured above (orphan bnode subjects, etc.)
    for t in g:
        if t not in emitted:
            index.add(t)

    # Declare each module as an owl:Ontology and have the index import them.
    index_ontology = URIRef(aggregate_ontology_iri(base_iri))
    index.add((index_ontology, RDF.type, OWL.Ontology))
    for mod in modules:
        modules[mod].add((URIRef(mod), RDF.type, OWL.Ontology))
        index.add((index_ontology, OWL.imports, URIRef(mod)))

    return modules, index


def stamp_versions(graph: Graph, model, release_label: str | None = None,
                   aggregate: bool = False) -> None:
    """Add OWL version metadata and YANG provenance to a graph.

    For each module IRI with subjects in `graph`, stamps the module ontology node
    with its `revision` (when it has one), its YANG-sourced dcterms metadata, and
    the provenance recording what the IRI was derived from.

    If aggregate=True and release_label is given, also adds owl:versionIRI and
    owl:versionInfo to the aggregate ontology.

    Args:
        graph: The RDF graph to stamp.
        model: The Model with .module_iris, .revisions, .module_yang_namespace.
        release_label: Optional release label (e.g. "Rel-19").
        aggregate: Whether this is an aggregate ontology graph (for versionIRI).
    """
    # Which modules have subjects present in this graph?
    candidates = module_prefix_map(
        model.base_iri, set(model.revisions) | set(model.module_iris))
    present = set()
    for s in graph.subjects():
        if isinstance(s, URIRef):
            mod = module_ns(s, candidates)
            if mod:
                present.add(mod)

    # Iterate the UNION, not just one source. Iterating only `revisions` (as the
    # old code did) skips metadata and provenance for a module with no
    # `revision` statement; iterating only `module_iris` would drop a module that
    # somehow carries a revision without being registered. Neither omission
    # should be silent.
    for mod in sorted(set(model.module_iris) | set(model.revisions)):
        if mod not in present:
            continue
        graph.add((URIRef(mod), RDF.type, OWL.Ontology))
        if mod in model.revisions:
            date, cr_ref = model.revisions[mod]
            version_string = f"revision {date}"
            if cr_ref:
                version_string += f" ({cr_ref})"
            graph.add((URIRef(mod), OWL.versionInfo, Literal(version_string)))
        _stamp_module_meta(graph, mod, model)
        _stamp_yang_provenance(graph, mod, model)

    # Aggregate ontology: title/description (derived from the YANG) + version.
    if aggregate:
        index_ontology = URIRef(aggregate_ontology_iri(model.base_iri))
        graph.add((index_ontology, RDF.type, OWL.Ontology))
        title, description = _aggregate_title(model)
        graph.add((index_ontology, DCTERMS.title, Literal(title)))
        graph.add((index_ontology, RDFS.label, Literal(title)))
        if description:
            graph.add((index_ontology, DCTERMS.description, Literal(description)))
        publishers = {m.organization for m in model.module_meta.values() if m.organization}
        for pub in sorted(publishers):
            graph.add((index_ontology, DCTERMS.publisher, Literal(pub)))
        if release_label:
            graph.add((index_ontology, OWL.versionIRI,
                       URIRef(version_iri(model.base_iri, release_label))))
            graph.add((index_ontology, OWL.versionInfo, Literal(release_label)))


def _stamp_yang_provenance(graph: Graph, mod: str, model) -> None:
    """Record what a module IRI was derived from (spec D6).

    `y2r:yangModuleName` and `y2r:yangNamespace` are minted by this project and
    assert no external authority. They exist because module identity is keyed on
    the declared module name, so the module's YANG `namespace` would otherwise be
    discarded — and in the 3GPP Rel-19 set two namespaces disagree with their
    module name, making this the only record of the original URN.
    """
    y2r = vocab_namespace(model.base_iri)
    meta = model.module_meta.get(mod)
    if meta is not None:
        graph.add((URIRef(mod), y2r.yangModuleName, Literal(meta.name)))
    urn = model.module_yang_namespace.get(mod)
    if urn:
        # A URN is a legal IRI, so this is emitted as a URIRef, not a string.
        graph.add((URIRef(mod), y2r.yangNamespace, URIRef(urn)))


def _aggregate_title(model) -> tuple[str, str]:
    """Title + description for the aggregate ontology, derived from the modules'
    own `reference` statements (e.g. the common 3GPP TS number) so the metadata
    comes from the input rather than being invented. Falls back to a generic
    label if no references are present."""
    from collections import Counter

    refs = Counter(m.reference for m in model.module_meta.values() if m.reference)
    n_modules = len(model.module_iris)
    if refs:
        # Most common reference — collapse to its first line (the TS title).
        top_ref = refs.most_common(1)[0][0].splitlines()[0].strip()
        title = f"{top_ref} — RDF/OWL ontology"
        description = (
            f"RDF/OWL ontology generated from {n_modules} YANG modules. "
            f"Primary source: {top_ref}."
        )
    else:
        title = "YANG-derived RDF/OWL ontology"
        description = f"RDF/OWL ontology generated from {n_modules} YANG modules."
    return title, description
