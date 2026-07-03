"""Convert YANG IR to SHACL shapes (validation constraints)."""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF, RDFS, XSD

from yang_to_rdf.namespace import class_iri, module_base_iri, property_iri
from yang_to_rdf.rdf_converter import IETF_TYPE_MAP, YANG_TO_XSD, NRM, NRM_SUBMODULE_BASE, _3GPP_COMMON_TYPES
from yang_to_rdf.yang_parser import Augment, Choice, Grouping, Leaf, ListNode, YangModule

SH = Namespace("http://www.w3.org/ns/shacl#")


class YangToSHACLConverter:
    def __init__(
        self,
        modules: list[YangModule],
        base_namespace: str | None = None,
        output_dir: str = "output",
        submodule_groupings: dict | None = None,
    ):
        self.modules = modules
        self.base_override = base_namespace
        self.output_dir = output_dir
        self.graph = Graph()
        self._bind_prefixes()
        self._grouping_bases: dict[str, str] = {}
        self._submodule_groupings = submodule_groupings or {}
        self._build_grouping_index()

    def _bind_prefixes(self):
        self.graph.bind("sh", SH)
        self.graph.bind("rdfs", RDFS)
        self.graph.bind("rdf", RDF)
        self.graph.bind("xsd", XSD)
        self.graph.bind("nrm", NRM)

    def _build_grouping_index(self):
        for mod in self.modules:
            base = module_base_iri(mod.namespace, self.base_override)
            for grp in mod.groupings:
                self._grouping_bases[grp.name] = base
        for grp_name in self._submodule_groupings:
            if not grp_name.startswith("typedef:") and grp_name not in self._grouping_bases:
                self._grouping_bases[grp_name] = NRM_SUBMODULE_BASE

    def convert(self) -> Graph:
        for mod in self.modules:
            base = module_base_iri(mod.namespace, self.base_override)
            self._convert_module(mod, base)
        return self.graph

    def _convert_module(self, mod: YangModule, base: str):
        ioc_groupings = self._identify_ioc_groupings(mod)
        for grp in mod.groupings:
            if grp.name in ioc_groupings:
                self._emit_shape(grp, base)

    def _identify_ioc_groupings(self, mod: YangModule) -> set[str]:
        augment_list_names = set()
        for aug in mod.augments:
            for lst in aug.lists:
                augment_list_names.add(lst.name)
        ioc_grps = set()
        for grp in mod.groupings:
            if grp.name.endswith("Grp"):
                ioc_name = grp.name[:-3]
                if ioc_name in augment_list_names:
                    ioc_grps.add(grp.name)
        return ioc_grps

    def _emit_shape(self, grp: Grouping, base: str):
        ioc_name = grp.name[:-3] if grp.name.endswith("Grp") else grp.name
        cls_uri = URIRef(class_iri(base, ioc_name))
        shape = URIRef(class_iri(base, f"{ioc_name}Shape"))
        g = self.graph

        g.add((shape, RDF.type, SH.NodeShape))
        g.add((shape, SH.targetClass, cls_uri))

        # Leaf properties
        for leaf in grp.leaves:
            self._emit_property_shape(shape, leaf, ioc_name, base)

        # Leaf-list properties
        for leaf in grp.leaf_lists:
            self._emit_property_shape(shape, leaf, ioc_name, base)

        # List properties
        for lst in grp.lists:
            self._emit_list_shape(shape, lst, ioc_name, base)

        # Choices → sh:xone
        for choice in grp.choices:
            self._emit_choice_shape(shape, choice, ioc_name, base)

    def _emit_property_shape(self, shape: URIRef, leaf: Leaf, class_name: str, base: str):
        if leaf.name == "idx":
            return

        g = self.graph
        prop_uri = URIRef(property_iri(base, class_name, leaf.name))
        prop_shape = BNode()

        g.add((shape, SH.property, prop_shape))
        g.add((prop_shape, SH.path, prop_uri))

        # Datatype
        xsd_type = self._resolve_type(leaf.type_name)
        if xsd_type and not leaf.enums:
            g.add((prop_shape, SH.datatype, xsd_type))

        # Cardinality
        if leaf.mandatory:
            g.add((prop_shape, SH.minCount, Literal(1)))
        elif leaf.min_elements is not None and leaf.min_elements > 0:
            g.add((prop_shape, SH.minCount, Literal(leaf.min_elements)))

        if not leaf.is_list:
            g.add((prop_shape, SH.maxCount, Literal(1)))
        elif leaf.max_elements is not None:
            g.add((prop_shape, SH.maxCount, Literal(leaf.max_elements)))

        # Enumerations → sh:in
        if leaf.enums:
            enum_list = BNode()
            Collection(g, enum_list, [Literal(e) for e in leaf.enums])
            g.add((prop_shape, SH["in"], enum_list))

        # Pattern
        if leaf.pattern:
            g.add((prop_shape, SH.pattern, Literal(leaf.pattern)))

        # Description
        if leaf.description:
            g.add((prop_shape, SH.description, Literal(leaf.description)))

    def _emit_list_shape(self, shape: URIRef, lst: ListNode, class_name: str, base: str):
        if lst.name == "idx":
            return

        g = self.graph
        prop_uri = URIRef(property_iri(base, class_name, lst.name))
        prop_shape = BNode()

        g.add((shape, SH.property, prop_shape))
        g.add((prop_shape, SH.path, prop_uri))

        if lst.min_elements is not None and lst.min_elements > 0:
            g.add((prop_shape, SH.minCount, Literal(lst.min_elements)))
        if lst.max_elements is not None:
            g.add((prop_shape, SH.maxCount, Literal(lst.max_elements)))

        # Point to nested class shape if uses a known grouping
        for used in lst.uses:
            local = used.split(":")[-1]
            grp_base = self._grouping_bases.get(local)
            if grp_base and local.endswith("Grp"):
                range_name = local[:-3]
                g.add((prop_shape, SH["class"], URIRef(class_iri(grp_base, range_name))))
                break

        if lst.description:
            g.add((prop_shape, SH.description, Literal(lst.description)))

    def _emit_choice_shape(self, shape: URIRef, choice: Choice, class_name: str, base: str):
        """Emit sh:xone for mutually exclusive cases."""
        g = self.graph
        case_shapes = []
        for case_name, leaves in choice.cases.items():
            case_shape = BNode()
            g.add((case_shape, RDF.type, SH.NodeShape))
            for leaf in leaves:
                prop_uri = URIRef(property_iri(base, class_name, leaf.name))
                ps = BNode()
                g.add((case_shape, SH.property, ps))
                g.add((ps, SH.path, prop_uri))
                g.add((ps, SH.minCount, Literal(1)))
            case_shapes.append(case_shape)

        if case_shapes:
            xone_list = BNode()
            Collection(g, xone_list, case_shapes)
            g.add((shape, SH.xone, xone_list))

    def _resolve_type(self, type_name: str) -> URIRef | None:
        if type_name in YANG_TO_XSD:
            return YANG_TO_XSD[type_name]
        if type_name in IETF_TYPE_MAP:
            return IETF_TYPE_MAP[type_name]
        if type_name == "enumeration":
            return XSD.string
        return None
