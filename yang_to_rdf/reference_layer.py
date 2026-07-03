# yang_to_rdf/reference_layer.py
"""Separate, auditable extension graph: inferred ranges for DN references."""
from __future__ import annotations

import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDFS

from yang_to_rdf.namespace import class_iri, property_iri
from yang_to_rdf.rdf_converter import NRM
from yang_to_rdf.yang_parser import Model

_SUFFIX = re.compile(r"(RefList|Refs|Ref|List)$")


class ReferenceLayerBuilder:
    def __init__(self, model: Model):
        self.model = model
        self.graph = Graph()
        self.graph.bind("rdfs", RDFS)
        self.graph.bind("nrm", NRM)
        self._by_name: dict[str, str] = {}
        for cls in model.classes:
            if cls.kind == "ioc":
                self._by_name.setdefault(
                    cls.name, class_iri(cls.namespace + "/", cls.name))

    def _candidate(self, leaf_name: str) -> str | None:
        stub = _SUFFIX.sub("", leaf_name)
        if not stub:
            return None
        return stub[0].upper() + stub[1:]

    def build(self) -> Graph:
        g = self.graph
        for cls in self.model.classes:
            base = cls.namespace + "/"
            for leaf in cls.leaves:
                if not leaf.is_reference:
                    continue
                prop = URIRef(property_iri(base, cls.name, leaf.name))
                cand = self._candidate(leaf.name)
                target = self._by_name.get(cand) if cand else None
                g.add((prop, NRM.inferredBy, Literal("dn-name-suffix")))
                if target is not None:
                    g.add((prop, RDFS.range, URIRef(target)))
                    g.add((prop, NRM.confidence, Literal("unambiguous")))
                else:
                    g.add((prop, NRM.confidence, Literal("unresolved")))
                    if cand:
                        g.add((prop, NRM.candidate, Literal(cand)))
        return g
