# yang_to_rdf/rdf_converter.py
"""Convert the resolved-tree IR to an RDFS/OWL TBox."""
from __future__ import annotations

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from yang_to_rdf.namespace import class_iri, property_iri
from yang_to_rdf.yang_parser import AttrRef, Klass, Leaf, Model, Typedef

NRM = Namespace("https://3gpp.org/nrm/vocab#")


class YangToRDFConverter:
    def __init__(self, model: Model):
        self.model = model
        self.graph = Graph()
        for p, ns in (("rdfs", RDFS), ("rdf", RDF), ("owl", OWL),
                      ("xsd", XSD), ("nrm", NRM)):
            self.graph.bind(p, ns)

    def convert(self) -> Graph:
        self._emit_vocab()
        for td in self.model.typedefs:
            self._emit_typedef(td)
        for cls in self.model.classes:
            self._emit_class(cls)
        return self.graph

    def _emit_vocab(self):
        g = self.graph
        g.add((NRM.nameContains, RDF.type, OWL.ObjectProperty))
        g.add((NRM.hasAttribute, RDF.type, OWL.ObjectProperty))
        g.add((NRM.ManagedFunction, RDF.type, RDFS.Class))
        g.add((NRM.isReference, RDF.type, OWL.ObjectProperty))
        g.add((NRM.isInvariant, RDF.type, OWL.DatatypeProperty))

    def _base(self, ns: str) -> str:
        return ns + "/"

    def _emit_typedef(self, td: Typedef):
        uri = URIRef(class_iri(self._base(td.namespace), td.name))
        self.graph.add((uri, RDF.type, RDFS.Datatype))
        if td.description:
            self.graph.add((uri, RDFS.comment, Literal(td.description)))

    def _emit_class(self, cls: Klass):
        g = self.graph
        base = self._base(cls.namespace)
        uri = URIRef(class_iri(base, cls.name))
        g.add((uri, RDF.type, RDFS.Class))
        if cls.description:
            g.add((uri, RDFS.comment, Literal(cls.description)))
        for parent in cls.subclass_of:
            g.add((uri, RDFS.subClassOf, URIRef(parent)))
        for child_iri in cls.contains:
            g.add((uri, NRM.nameContains, URIRef(child_iri)))
        for leaf in cls.leaves:
            self._emit_leaf(leaf, cls, base, uri)
        for ref in cls.attr_refs:
            self._emit_attr_ref(ref, cls, base, uri)

    def _emit_leaf(self, leaf: Leaf, cls: Klass, base: str, cls_uri: URIRef):
        g = self.graph
        prop = URIRef(property_iri(base, cls.name, leaf.name))
        if leaf.is_reference:
            g.add((prop, RDF.type, OWL.ObjectProperty))
            g.add((prop, NRM.isReference, Literal(True)))
        else:
            g.add((prop, RDF.type, RDF.Property))
            if leaf.xsd is not None:
                g.add((prop, RDFS.range, leaf.xsd))
        g.add((prop, RDFS.domain, cls_uri))
        if leaf.description:
            g.add((prop, RDFS.comment, Literal(leaf.description)))
        if leaf.is_invariant:
            g.add((prop, NRM.isInvariant, Literal(True)))

    def _emit_attr_ref(self, ref: AttrRef, cls: Klass, base: str, cls_uri: URIRef):
        g = self.graph
        prop = URIRef(property_iri(base, cls.name, ref.name))
        target = URIRef(ref.target_iri)
        g.add((prop, RDF.type, OWL.ObjectProperty))
        g.add((prop, RDFS.domain, cls_uri))
        g.add((prop, RDFS.range, target))
        g.add((cls_uri, NRM.hasAttribute, target))
        if ref.description:
            g.add((prop, RDFS.comment, Literal(ref.description)))
