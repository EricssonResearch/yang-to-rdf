# yang_to_rdf/shacl_converter.py
"""Convert the resolved-tree IR to SHACL NodeShapes (IOCs + dataType classes)."""
from __future__ import annotations

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF, RDFS, XSD

from yang_to_rdf.namespace import class_iri, property_iri
from yang_to_rdf.rdf_converter import NRM
from yang_to_rdf.yang_parser import AttrRef, Klass, Leaf, Model

SH = Namespace("http://www.w3.org/ns/shacl#")


class YangToSHACLConverter:
    def __init__(self, model: Model):
        self.model = model
        self.graph = Graph()
        for p, ns in (("sh", SH), ("rdfs", RDFS), ("rdf", RDF),
                      ("xsd", XSD), ("nrm", NRM)):
            self.graph.bind(p, ns)

    def convert(self) -> Graph:
        for cls in self.model.classes:
            self._emit_shape(cls)
        return self.graph

    def _emit_shape(self, cls: Klass):
        g = self.graph
        base = cls.namespace + "/"
        cls_uri = URIRef(class_iri(base, cls.name))
        shape = URIRef(class_iri(base, f"{cls.name}Shape"))
        g.add((shape, RDF.type, SH.NodeShape))
        g.add((shape, SH.targetClass, cls_uri))
        for i, leaf in enumerate(cls.leaves):
            self._emit_leaf_shape(shape, leaf, cls, base, i)
        for i, ref in enumerate(cls.attr_refs, start=len(cls.leaves)):
            self._emit_attr_shape(shape, ref, cls, base, i)

    def _emit_leaf_shape(self, shape, leaf: Leaf, cls: Klass, base: str, idx: int):
        g = self.graph
        # Use deterministic BNode ID based on shape URI and index
        ps = BNode(f"{shape}_prop_{idx}")
        g.add((shape, SH.property, ps))
        g.add((ps, SH.path, URIRef(property_iri(base, cls.name, leaf.name))))
        if leaf.xsd is not None and not leaf.enums and not leaf.is_reference:
            g.add((ps, SH.datatype, leaf.xsd))
        if leaf.mandatory:
            g.add((ps, SH.minCount, Literal(1)))
        elif leaf.min_elements:
            g.add((ps, SH.minCount, Literal(leaf.min_elements)))
        if not leaf.is_list:
            g.add((ps, SH.maxCount, Literal(1)))
        elif leaf.max_elements is not None:
            g.add((ps, SH.maxCount, Literal(leaf.max_elements)))
        if leaf.enums:
            lst = BNode(f"{shape}_prop_{idx}_enumlist")
            Collection(g, lst, [Literal(e) for e in leaf.enums])
            g.add((ps, SH["in"], lst))
        if leaf.pattern:
            g.add((ps, SH.pattern, Literal(leaf.pattern)))
        if leaf.description:
            g.add((ps, SH.description, Literal(leaf.description)))

    def _emit_attr_shape(self, shape, ref: AttrRef, cls: Klass, base: str, idx: int):
        g = self.graph
        # Use deterministic BNode ID based on shape URI and index
        ps = BNode(f"{shape}_prop_{idx}")
        g.add((shape, SH.property, ps))
        g.add((ps, SH.path, URIRef(property_iri(base, cls.name, ref.name))))
        g.add((ps, SH["class"], URIRef(ref.target_iri)))
        if ref.min_elements:
            g.add((ps, SH.minCount, Literal(ref.min_elements)))
        if ref.max_elements is not None:
            g.add((ps, SH.maxCount, Literal(ref.max_elements)))
        if ref.description:
            g.add((ps, SH.description, Literal(ref.description)))
