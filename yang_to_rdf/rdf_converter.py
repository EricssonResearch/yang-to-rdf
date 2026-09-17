# yang_to_rdf/rdf_converter.py
"""Convert the resolved-tree IR to an RDFS/OWL TBox."""
from __future__ import annotations

from collections import Counter

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from yang_to_rdf.namespace import (
    bind_standard_namespaces,
    class_iri,
    namespace_base,
    property_iri,
    vocab_namespace,
)
from yang_to_rdf.output_writer import module_stem
from yang_to_rdf.yang_parser import AttrRef, Klass, Leaf, Model, Typedef


class YangToRDFConverter:
    def __init__(self, model: Model):
        self.model = model
        self.y2r = vocab_namespace(model.base_iri)
        self.graph = Graph()
        bind_standard_namespaces(self.graph, model.base_iri)
        self._labels = self._assign_labels()

    def _assign_labels(self) -> dict[str, str]:
        """Human-readable, GLOBALLY UNIQUE rdfs:label per class/typedef, by IRI.

        Local names are heavily reused across modules (e.g. `PerfMetricJob` on ~46
        IOCs are distinct classes), so a bare local name is neither unique nor a
        usable HTML anchor for documentation tools. Rule: bare `Name` when the name
        is unique across the whole model; else qualify with the module stem
        (`_3gpp-5gc-nrm-amffunction:PerfMetricJob`); if that still collides (same name in the same
        module), append a `#N` suffix. Classes and typedefs share one label space.
        Deterministic (terms processed in model order, which is sorted by module).
        """
        terms = [(class_iri(namespace_base(c.namespace), c.name), c.name)
                 for c in self.model.classes]
        terms += [(class_iri(namespace_base(t.namespace), t.name), t.name)
                  for t in self.model.typedefs]
        name_counts = Counter(name for _, name in terms)
        stem = {class_iri(namespace_base(c.namespace), c.name): module_stem(c.namespace)
                for c in self.model.classes}
        stem.update({class_iri(namespace_base(t.namespace), t.name): module_stem(t.namespace)
                     for t in self.model.typedefs})

        labels: dict[str, str] = {}
        used: set[str] = set()
        for iri, name in terms:
            if iri in labels:
                continue
            base = name if name_counts[name] == 1 else f"{stem[iri]}:{name}"
            label = base
            n = 2
            while label in used:
                label = f"{base}#{n}"
                n += 1
            used.add(label)
            labels[iri] = label
        return labels

    def _class_label(self, cls: Klass) -> str:
        return self._labels[class_iri(namespace_base(cls.namespace), cls.name)]

    def convert(self) -> Graph:
        self._emit_vocab()
        for td in self.model.typedefs:
            self._emit_typedef(td)
        for cls in self.model.classes:
            self._emit_class(cls)
        return self.graph

    def _emit_vocab(self):
        g = self.graph
        g.add((self.y2r.nameContains, RDF.type, OWL.ObjectProperty))
        g.add((self.y2r.hasAttribute, RDF.type, OWL.ObjectProperty))
        g.add((self.y2r.ManagedFunction, RDF.type, RDFS.Class))
        g.add((self.y2r.isReference, RDF.type, OWL.ObjectProperty))
        g.add((self.y2r.isInvariant, RDF.type, OWL.DatatypeProperty))

    def _emit_typedef(self, td: Typedef):
        uri = URIRef(class_iri(namespace_base(td.namespace), td.name))
        self.graph.add((uri, RDF.type, RDFS.Datatype))
        self.graph.add((uri, RDFS.label, Literal(self._labels[str(uri)])))
        if td.description:
            self.graph.add((uri, RDFS.comment, Literal(td.description)))

    def _emit_class(self, cls: Klass):
        g = self.graph
        base = namespace_base(cls.namespace)
        uri = URIRef(class_iri(base, cls.name))
        label = self._class_label(cls)
        g.add((uri, RDF.type, RDFS.Class))
        g.add((uri, RDFS.label, Literal(label)))
        if cls.description:
            g.add((uri, RDFS.comment, Literal(cls.description)))
        for parent in cls.subclass_of:
            g.add((uri, RDFS.subClassOf, URIRef(parent)))
        for child_iri in cls.contains:
            g.add((uri, self.y2r.nameContains, URIRef(child_iri)))
        for leaf in cls.leaves:
            self._emit_leaf(leaf, cls, base, uri)
        for ref in cls.attr_refs:
            self._emit_attr_ref(ref, cls, base, uri)

    def _emit_leaf(self, leaf: Leaf, cls: Klass, base: str, cls_uri: URIRef):
        g = self.graph
        prop = URIRef(property_iri(base, cls.name, leaf.name))
        if leaf.is_reference:
            g.add((prop, RDF.type, OWL.ObjectProperty))
            g.add((prop, self.y2r.isReference, Literal(True)))
        else:
            g.add((prop, RDF.type, RDF.Property))
            if leaf.xsd is not None:
                g.add((prop, RDFS.range, leaf.xsd))
        g.add((prop, RDFS.label, Literal(f"{self._class_label(cls)}.{leaf.name}")))
        g.add((prop, RDFS.domain, cls_uri))
        if leaf.description:
            g.add((prop, RDFS.comment, Literal(leaf.description)))
        if leaf.is_invariant:
            g.add((prop, self.y2r.isInvariant, Literal(True)))

    def _emit_attr_ref(self, ref: AttrRef, cls: Klass, base: str, cls_uri: URIRef):
        g = self.graph
        prop = URIRef(property_iri(base, cls.name, ref.name))
        target = URIRef(ref.target_iri)
        g.add((prop, RDF.type, OWL.ObjectProperty))
        g.add((prop, RDFS.label, Literal(f"{self._class_label(cls)}.{ref.name}")))
        g.add((prop, RDFS.domain, cls_uri))
        g.add((prop, RDFS.range, target))
        g.add((cls_uri, self.y2r.hasAttribute, target))
        if ref.description:
            g.add((prop, RDFS.comment, Literal(ref.description)))
