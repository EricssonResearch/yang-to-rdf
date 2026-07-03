"""Convert YANG IR to RDF TBox (RDFS classes, properties, subClassOf, containment)."""

from __future__ import annotations

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from yang_to_rdf.namespace import class_iri, module_base_iri, property_iri
from yang_to_rdf.yang_parser import Augment, Grouping, Leaf, ListNode, Typedef, YangModule

# 3GPP NRM vocabulary for containment
NRM = Namespace("https://3gpp.org/nrm/vocab#")

# Base IRI for submodule-defined classes (path-based, not fragment-based)
NRM_SUBMODULE_BASE = "https://3gpp.org/nrm/vocab/"

# YANG type → XSD datatype mapping
YANG_TO_XSD = {
    "string": XSD.string,
    "boolean": XSD.boolean,
    "uint8": XSD.unsignedByte,
    "uint16": XSD.unsignedShort,
    "uint32": XSD.unsignedInt,
    "uint64": XSD.unsignedLong,
    "int8": XSD.byte,
    "int16": XSD.short,
    "int32": XSD.int,
    "int64": XSD.long,
    "decimal64": XSD.decimal,
    "empty": XSD.boolean,
    "binary": XSD.base64Binary,
    "instance-identifier": XSD.anyURI,
    "leafref": XSD.anyURI,
    "union": XSD.string,
}

# Well-known IETF type mappings
IETF_TYPE_MAP = {
    "inet:ipv4-address": XSD.string,
    "inet:ipv6-address": XSD.string,
    "inet:domain-name": XSD.string,
    "inet:host": XSD.string,
    "inet:host-name": XSD.string,
    "inet:uri": XSD.anyURI,
    "yang:date-and-time": XSD.dateTime,
    "yang:hex-string": XSD.string,
    "yang:counter64": XSD.unsignedLong,
    "yang:gauge64": XSD.unsignedLong,
}

# Groupings that signal inheritance from ManagedFunction
MANAGED_FUNCTION_GRPS = {"mf3gpp:ManagedFunctionGrp", "ManagedFunctionGrp"}


# Well-known 3GPP typedef mappings (from _3gpp-common-yang-types, not always in input)
_3GPP_COMMON_TYPES = {
    "DistinguishedName": XSD.string,
    "Dn": XSD.string,
    "LDN": XSD.string,
    "Mcc": XSD.string,
    "Mnc": XSD.string,
    "Tac": XSD.string,
    "EutraCellId": XSD.string,
    "CagId": XSD.string,
    "Fqdn": XSD.string,
}


class YangToRDFConverter:
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
        # Map grouping name → module base IRI (for cross-module resolution)
        self._grouping_bases: dict[str, str] = {}
        # Map typedef name → (module base IRI, typedef) for cross-module type resolution
        self._typedef_index: dict[str, tuple[str, Typedef]] = {}
        self._submodule_groupings = submodule_groupings or {}
        self._build_grouping_index()

    def _bind_prefixes(self):
        self.graph.bind("rdfs", RDFS)
        self.graph.bind("rdf", RDF)
        self.graph.bind("owl", OWL)
        self.graph.bind("xsd", XSD)
        self.graph.bind("nrm", NRM)

    def _build_grouping_index(self):
        """Index all groupings and typedefs by name for cross-module resolution."""
        for mod in self.modules:
            base = module_base_iri(mod.namespace, self.base_override)
            for grp in mod.groupings:
                self._grouping_bases[grp.name] = base
            for td in mod.typedefs:
                self._typedef_index[td.name] = (base, td)
        # Include submodule groupings — use NRM base
        for grp_name, val in self._submodule_groupings.items():
            if grp_name.startswith("typedef:"):
                # Index submodule typedefs
                td_name = grp_name[len("typedef:"):]
                self._typedef_index[td_name] = (NRM_SUBMODULE_BASE, val)
            elif grp_name not in self._grouping_bases:
                self._grouping_bases[grp_name] = NRM_SUBMODULE_BASE

    def convert(self) -> Graph:
        """Run the full conversion, return the RDF graph."""
        # Emit NRM vocabulary terms
        self._emit_nrm_vocab()

        # First pass: collect containment relationships from augments
        self._containment_pairs: set[tuple[str, str]] = set()  # (parent_name, child_name)
        for mod in self.modules:
            base = module_base_iri(mod.namespace, self.base_override)
            for aug in mod.augments:
                target_parts = aug.target_path.strip("/").split("/")
                parent_local = target_parts[-1].split(":")[-1] if target_parts else ""
                for lst in aug.lists:
                    self._containment_pairs.add((parent_local, lst.name))

        # Second pass: emit everything
        for mod in self.modules:
            base = module_base_iri(mod.namespace, self.base_override)
            self._convert_module(mod, base)

        # Third pass: emit submodule groupings as classes with properties
        self._emit_submodule_groupings()

        # Post-process: ensure all range targets and nameContains participants are typed
        self._ensure_class_typing()

        return self.graph

    def _emit_submodule_groupings(self):
        """Emit classes and properties for groupings defined in submodules."""
        base = NRM_SUBMODULE_BASE
        for grp_name, grp in self._submodule_groupings.items():
            if grp_name.startswith("typedef:"):
                continue  # typedefs handled via _typedef_index
            # Derive class name: strip "Grp" suffix
            ioc_name = grp_name[:-3] if grp_name.endswith("Grp") else grp_name
            cls_uri = URIRef(class_iri(base, ioc_name))
            g = self.graph

            g.add((cls_uri, RDF.type, RDFS.Class))
            if grp.description:
                g.add((cls_uri, RDFS.comment, Literal(grp.description)))

            for leaf in grp.leaves:
                self._emit_leaf_property(leaf, ioc_name, base, cls_uri)
            for leaf in grp.leaf_lists:
                self._emit_leaf_property(leaf, ioc_name, base, cls_uri)
            for lst in grp.lists:
                self._emit_list_property(lst, ioc_name, base, cls_uri)

    def _ensure_class_typing(self):
        """Ensure every node referenced as range, nameContains, or subClassOf target is a class."""
        g = self.graph
        declared = set(g.subjects(RDF.type, RDFS.Class))
        xsd_ns = str(XSD)

        to_type = set()
        for _, _, o in g.triples((None, RDFS.range, None)):
            if o not in declared and not str(o).startswith(xsd_ns):
                to_type.add(o)
        for s, _, o in g.triples((None, NRM.nameContains, None)):
            if s not in declared:
                to_type.add(s)
            if o not in declared:
                to_type.add(o)
        for _, _, o in g.triples((None, RDFS.subClassOf, None)):
            if o not in declared:
                to_type.add(o)

        for node in to_type:
            g.add((node, RDF.type, RDFS.Class))

    def _emit_nrm_vocab(self):
        """Emit the small nrm: vocabulary for containment."""
        g = self.graph
        nc = NRM.nameContains
        g.add((nc, RDF.type, OWL.ObjectProperty))
        g.add((nc, RDFS.comment, Literal(
            "3GPP name-containment: parent IOC contains child IOC instances"
        )))
        ncb = NRM.nameContainedBy
        g.add((ncb, RDF.type, OWL.ObjectProperty))
        g.add((ncb, OWL.inverseOf, nc))
        # Declare ManagedFunction as a class (superclass for all NF IOCs)
        g.add((NRM.ManagedFunction, RDF.type, RDFS.Class))
        g.add((NRM.ManagedFunction, RDFS.comment, Literal(
            "Base class for all 3GPP managed network functions"
        )))

    def _convert_module(self, mod: YangModule, base: str):
        """Convert a single YANG module."""
        # Typedefs → rdfs:Class or rdfs:Datatype
        for td in mod.typedefs:
            self._emit_typedef(td, base)

        # Groupings that end in "Grp" and have a matching augment → IOC class
        ioc_groupings = self._identify_ioc_groupings(mod)

        for grp in mod.groupings:
            if grp.name in ioc_groupings:
                self._emit_ioc_class(grp, base)

        # Augments → containment relationships
        for aug in mod.augments:
            self._emit_augment(aug, base, mod)

    def _identify_ioc_groupings(self, mod: YangModule) -> set[str]:
        """Identify groupings that represent IOC classes.

        Heuristic: a grouping named XGrp where X appears as a list in an augment.
        """
        # Collect list names from augments
        augment_list_names = set()
        for aug in mod.augments:
            for lst in aug.lists:
                augment_list_names.add(lst.name)

        ioc_grps = set()
        for grp in mod.groupings:
            # Check if grouping name matches pattern: <IOCName>Grp or <IOCName>FunctionGrp
            candidate = grp.name
            if candidate.endswith("Grp"):
                ioc_name = candidate[:-3]  # strip "Grp"
                if ioc_name in augment_list_names:
                    ioc_grps.add(candidate)
        return ioc_grps

    def _emit_ioc_class(self, grp: Grouping, base: str):
        """Emit an IOC class from a grouping."""
        ioc_name = grp.name[:-3] if grp.name.endswith("Grp") else grp.name
        cls_uri = URIRef(class_iri(base, ioc_name))
        g = self.graph

        g.add((cls_uri, RDF.type, RDFS.Class))
        if grp.description:
            g.add((cls_uri, RDFS.comment, Literal(grp.description)))

        # Inheritance: uses of base groupings
        for used in grp.uses:
            if used in MANAGED_FUNCTION_GRPS or used.endswith("ManagedFunctionGrp"):
                # Resolve to ManagedFunction class
                g.add((cls_uri, RDFS.subClassOf, NRM.ManagedFunction))
            elif used.endswith("Grp"):
                # Try to resolve as another IOC
                parent_name = used.split(":")[-1][:-3]  # strip prefix: and Grp
                # Skip if this is a containment parent (not true inheritance)
                if (parent_name, ioc_name) in self._containment_pairs:
                    continue
                parent_base = self._resolve_grouping_base(used)
                if parent_base:
                    parent_uri = URIRef(class_iri(parent_base, parent_name))
                    g.add((cls_uri, RDFS.subClassOf, parent_uri))

        # Properties from leaves
        for leaf in grp.leaves:
            self._emit_leaf_property(leaf, ioc_name, base, cls_uri)

        # Properties from leaf-lists
        for leaf in grp.leaf_lists:
            self._emit_leaf_property(leaf, ioc_name, base, cls_uri)

        # Properties from lists (nested structures)
        for lst in grp.lists:
            self._emit_list_property(lst, ioc_name, base, cls_uri)

    def _emit_leaf_property(self, leaf: Leaf, class_name: str, base: str, cls_uri: URIRef):
        """Emit an rdf:Property for a leaf/leaf-list."""
        # Skip synthetic index keys
        if leaf.name == "idx":
            return

        prop_uri = URIRef(property_iri(base, class_name, leaf.name))
        g = self.graph

        g.add((prop_uri, RDF.type, RDF.Property))
        g.add((prop_uri, RDFS.domain, cls_uri))

        # Range
        xsd_type = self._resolve_type(leaf.type_name)
        if xsd_type:
            g.add((prop_uri, RDFS.range, xsd_type))

        if leaf.description:
            g.add((prop_uri, RDFS.comment, Literal(leaf.description)))

    def _emit_list_property(self, lst: ListNode, class_name: str, base: str, cls_uri: URIRef):
        """Emit an object property for a YANG list (nested structure)."""
        if lst.name == "idx":
            return

        prop_uri = URIRef(property_iri(base, class_name, lst.name))
        g = self.graph

        g.add((prop_uri, RDF.type, RDF.Property))
        g.add((prop_uri, RDFS.domain, cls_uri))

        if lst.description:
            g.add((prop_uri, RDFS.comment, Literal(lst.description)))

        # If the list uses a known grouping, point range to that class
        for used in lst.uses:
            local = used.split(":")[-1]
            grp_base = self._grouping_bases.get(local)
            if grp_base:
                # Strip "Grp" suffix if present for the class name
                range_name = local[:-3] if local.endswith("Grp") else local
                g.add((prop_uri, RDFS.range, URIRef(class_iri(grp_base, range_name))))
                break

    def _emit_augment(self, aug: Augment, base: str, mod: YangModule):
        """Emit containment relationships from augment statements."""
        g = self.graph
        # Parse target: e.g. "/me3gpp:ManagedElement" → ManagedElement
        target_parts = aug.target_path.strip("/").split("/")
        parent_local = target_parts[-1].split(":")[-1] if target_parts else "Unknown"

        # Resolve parent IRI — try to find it in imports
        parent_uri = self._resolve_augment_target(parent_local, aug.target_path, mod)

        # Ensure the parent is declared as a class
        g.add((parent_uri, RDF.type, RDFS.Class))

        for lst in aug.lists:
            child_uri = URIRef(class_iri(base, lst.name))
            g.add((parent_uri, NRM.nameContains, child_uri))

    def _resolve_augment_target(
        self, local_name: str, full_path: str, mod: YangModule
    ) -> URIRef:
        """Resolve the augment target to an IRI."""
        # For 3GPP NRM, common targets are ManagedElement, SubNetwork
        # Try to find via imported module groupings
        target_parts = full_path.strip("/").split("/")
        if target_parts:
            prefixed = target_parts[-1]
            if ":" in prefixed:
                pfx, name = prefixed.split(":", 1)
                if pfx in mod.imports:
                    imported_mod = mod.imports[pfx]
                    # Look up the base for that module's groupings
                    for grp_name, grp_base in self._grouping_bases.items():
                        if grp_name == f"{name}Grp" or grp_name == name:
                            return URIRef(class_iri(grp_base, name))
        # Fallback: use NRM namespace
        return URIRef(f"{NRM}{local_name}")

    def _emit_typedef(self, td: Typedef, base: str):
        """Emit a typedef as rdfs:Class."""
        td_uri = URIRef(class_iri(base, td.name))
        g = self.graph
        g.add((td_uri, RDF.type, RDFS.Class))
        if td.description:
            g.add((td_uri, RDFS.comment, Literal(td.description)))

    def _resolve_type(self, type_name: str) -> URIRef | None:
        """Map a YANG type to an XSD datatype URI or a typedef class URI."""
        if type_name in YANG_TO_XSD:
            return YANG_TO_XSD[type_name]
        if type_name in IETF_TYPE_MAP:
            return IETF_TYPE_MAP[type_name]
        if type_name == "enumeration":
            return XSD.string
        # Prefixed type reference (e.g. types3gpp:DistinguishedName)
        local = type_name.split(":")[-1] if ":" in type_name else type_name
        # Check parsed typedefs
        if local in self._typedef_index:
            base, td = self._typedef_index[local]
            return URIRef(class_iri(base, td.name))
        # Fallback: well-known 3GPP common types
        if local in _3GPP_COMMON_TYPES:
            return _3GPP_COMMON_TYPES[local]
        return None

    def _resolve_grouping_base(self, uses_ref: str) -> str | None:
        """Resolve a uses reference (possibly prefixed) to its module base IRI."""
        local = uses_ref.split(":")[-1]
        return self._grouping_bases.get(local)
