# yang_to_rdf/reference_layer.py
"""Separate, auditable extension graph: inferred ranges for DN references."""
from __future__ import annotations

import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDFS

from yang_to_rdf.namespace import (
    bind_standard_namespaces,
    class_iri,
    namespace_base,
    property_iri,
    vocab_namespace,
)
from yang_to_rdf.yang_parser import Model

_SUFFIX = re.compile(r"(RefList|Refs|Ref|List)$")


class ReferenceLayerBuilder:
    """Builds the separate, opt-out reference-inference layer (`*_refs.ttl`).

    DistinguishedName references have no schema-declared target, so the base TBox
    leaves their range open. This builder *guesses* the target IOC by stripping a
    Ref/RefList suffix from the leaf name (see _candidate) and matching it against
    known IOC class names, tagging every guess with nrm:confidence provenance so
    the heuristic stays auditable and quarantined from the base output.
    """

    def __init__(self, model: Model):
        self.model = model
        self.y2r = vocab_namespace(model.base_iri)
        self.graph = Graph()
        bind_standard_namespaces(self.graph, model.base_iri)
        self._by_name: dict[str, list[str]] = {}
        for cls in model.classes:
            if cls.kind == "ioc":
                self._by_name.setdefault(cls.name, []).append(
                    class_iri(namespace_base(cls.namespace), cls.name))

    def _candidate(self, leaf_name: str) -> str | None:
        """Guess the target IOC class name from a DN reference leaf name.

        Strips a trailing Ref/Refs/RefList/List and upper-cases the first letter,
        e.g. `aMFSetRef` -> `AMFSet`. Returns None if nothing remains.
        """
        stub = _SUFFIX.sub("", leaf_name)
        if not stub:
            return None
        return stub[0].upper() + stub[1:]

    def build(self) -> Graph:
        g = self.graph
        for cls in self.model.classes:
            base = namespace_base(cls.namespace)
            for leaf in cls.leaves:
                if not leaf.is_reference:
                    continue
                prop = URIRef(property_iri(base, cls.name, leaf.name))
                cand = self._candidate(leaf.name)
                matches = self._by_name.get(cand, []) if cand else []
                g.add((prop, self.y2r.inferredBy, Literal("dn-name-suffix")))
                if len(matches) == 1:
                    g.add((prop, RDFS.range, URIRef(matches[0])))
                    g.add((prop, self.y2r.confidence, Literal("unambiguous")))
                else:
                    g.add((prop, self.y2r.confidence, Literal("unresolved")))
                    if cand:
                        g.add((prop, self.y2r.candidate, Literal(cand)))
        return g
