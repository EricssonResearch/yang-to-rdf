"""Build an RDF-oriented IR from pyang's *resolved* schema tree."""
from __future__ import annotations

from dataclasses import dataclass, field

from yang_to_rdf.namespace import class_iri
from yang_to_rdf.pyang_context import build_context
from yang_to_rdf.type_resolver import resolve_type

INVARIANT_EXT = ("_3gpp-common-yang-extensions", "inVariant")
MANAGED_FUNCTION_GRP = "ManagedFunctionGrp"
MANAGED_FUNCTION_IRI = "https://3gpp.org/nrm/vocab#ManagedFunction"
BASE_GROUPINGS = {
    "Top_Grp",
    "ManagedFunctionGrp",
    "ManagedElementGrp",
    "SubNetworkGrp",
    "ManagedFunctionContainedClasses",
    "DomainGrp",
}


@dataclass
class Leaf:
    name: str
    type_name: str = "string"
    description: str = ""
    mandatory: bool = False
    is_list: bool = False
    min_elements: int | None = None
    max_elements: int | None = None
    enums: list[str] = field(default_factory=list)
    pattern: str | None = None
    xsd: object | None = None
    is_reference: bool = False
    is_invariant: bool = False


@dataclass
class AttrRef:
    name: str
    target_iri: str
    min_elements: int | None = None
    max_elements: int | None = None
    description: str = ""


@dataclass
class Klass:
    name: str
    namespace: str
    kind: str  # "ioc" | "datatype"
    description: str = ""
    subclass_of: list[str] = field(default_factory=list)
    leaves: list[Leaf] = field(default_factory=list)
    attr_refs: list[AttrRef] = field(default_factory=list)
    contains: list[str] = field(default_factory=list)


@dataclass
class Typedef:
    name: str
    namespace: str
    enums: list[str] = field(default_factory=list)
    pattern: str | None = None
    description: str = ""


@dataclass
class Model:
    classes: list[Klass] = field(default_factory=list)
    typedefs: list[Typedef] = field(default_factory=list)
    revisions: dict[str, tuple[str, str | None]] = field(default_factory=dict)

    @property
    def iocs(self) -> list[Klass]:
        return [c for c in self.classes if c.kind == "ioc"]


def _ns(stmt) -> str:
    m = stmt.i_module if getattr(stmt, "i_module", None) is not None else stmt
    n = m.search_one("namespace")
    return n.arg if n is not None else ""


def _desc(stmt) -> str:
    d = stmt.search_one("description")
    return d.arg if d is not None else ""


def _int(stmt, kw) -> int | None:
    s = stmt.search_one(kw)
    return int(s.arg) if s is not None else None


def _has_invariant(stmt) -> bool:
    return any(
        isinstance(s.keyword, tuple) and s.keyword == INVARIANT_EXT
        for s in stmt.substmts
    )


def _attributes_container(list_node):
    for c in getattr(list_node, "i_children", []):
        if c.keyword == "container" and c.arg == "attributes":
            return c
    return None


def _is_ioc(list_node) -> bool:
    return _attributes_container(list_node) is not None


def _grouping_home_ns(u, ctx):
    """Resolve the home module namespace for a uses statement's grouping."""
    g = getattr(u, "i_grouping", None)
    if g is None:
        return None
    m = getattr(g, "i_module", None)
    if m is None:
        return None
    ns = m.search_one("namespace")
    if ns is not None:
        return ns.arg  # defining module
    bt = m.search_one("belongs-to")  # submodule -> parent module namespace
    if bt is not None:
        parent = ctx.get_module(bt.arg)
        if parent is not None and parent.search_one("namespace") is not None:
            return parent.search_one("namespace").arg
    return None


def _class_identity(list_node, ctx):
    """Compute (name, namespace, iri) identity for a list node's class.

    If the node uses exactly one non-base grouping ending with 'Grp',
    derive from that grouping. Otherwise fallback to node-based naming.
    """
    # Collect resolved uses statements
    uses_stmts = [s for s in list_node.substmts if s.keyword == "uses"]

    # Filter to real groupings (non-base, ends with 'Grp')
    real_groupings = []
    for u in uses_stmts:
        g = getattr(u, "i_grouping", None)
        if g is None:
            continue
        # Strip any prefix (e.g., "prefix:GroupingName" -> "GroupingName")
        local_name = g.arg.split(":")[-1]
        if local_name not in BASE_GROUPINGS and local_name.endswith("Grp"):
            real_groupings.append((u, local_name))

    # Rule: exactly one real grouping -> derive from it
    if len(real_groupings) == 1:
        u, local_name = real_groupings[0]
        class_name = local_name[:-3]  # strip 'Grp' suffix
        class_ns = _grouping_home_ns(u, ctx)
        if class_ns is not None:
            cls_iri = class_iri(class_ns + "/", class_name)
            return (class_name, class_ns, cls_iri)

    # Fallback: node-based naming
    ns = _ns(list_node)
    name = list_node.arg
    iri = class_iri(ns + "/", name)
    return (name, ns, iri)


def _leaf_from(stmt) -> Leaf:
    t = stmt.search_one("type")
    # anydata/anyxml have no 'type' and carry opaque content: leave xsd open.
    if t is None:
        return Leaf(
            name=stmt.arg,
            type_name=stmt.keyword,
            description=_desc(stmt),
            mandatory=False,
            is_list=stmt.keyword == "leaf-list",
            min_elements=_int(stmt, "min-elements"),
            max_elements=_int(stmt, "max-elements"),
            xsd=None,
            is_invariant=_has_invariant(stmt),
        )
    rt = resolve_type(t)
    mand = stmt.search_one("mandatory")
    return Leaf(
        name=stmt.arg,
        type_name=t.arg,
        description=_desc(stmt),
        mandatory=mand is not None and mand.arg == "true",
        is_list=stmt.keyword == "leaf-list",
        min_elements=_int(stmt, "min-elements"),
        max_elements=_int(stmt, "max-elements"),
        enums=rt.enums,
        pattern=rt.pattern,
        xsd=rt.xsd,
        is_reference=rt.is_reference,
        is_invariant=_has_invariant(stmt),
    )


def _grouping_uses_managed_function(grp) -> bool:
    if grp.arg == MANAGED_FUNCTION_GRP:
        return True
    for sub in grp.substmts:
        if sub.keyword == "uses":
            g2 = getattr(sub, "i_grouping", None)
            if g2 is not None and _grouping_uses_managed_function(g2):
                return True
    return False


def _subclasses(list_node) -> list[str]:
    out: list[str] = []
    scopes = [list_node]
    attrs = _attributes_container(list_node)
    if attrs is not None:
        scopes.append(attrs)
    for scope in scopes:
        for sub in scope.substmts:
            if sub.keyword == "uses":
                grp = getattr(sub, "i_grouping", None)
                if grp is not None and _grouping_uses_managed_function(grp):
                    if MANAGED_FUNCTION_IRI not in out:
                        out.append(MANAGED_FUNCTION_IRI)
    return out


class _Parser:
    def __init__(self):
        self.model = Model()
        self.seen: dict[str, Klass] = {}
        # keywords encountered inside a class that we deliberately do not model,
        # collected so nothing is dropped silently (surfaced by parse()).
        self.unhandled: set[str] = set()
        self.ctx = None  # set in run()

    def _register_datatype(self, list_node) -> str:
        """Register a nested dataType list as a class; return its IRI."""
        name, ns, iri = _class_identity(list_node, self.ctx)
        if iri in self.seen:
            return iri
        cls = Klass(name=name, namespace=ns, kind="datatype",
                    description=_desc(list_node))
        self.seen[iri] = cls
        self.model.classes.append(cls)
        self._fill_children(cls, list_node)
        return iri

    def _fill_children(self, cls: Klass, node) -> None:
        """Populate leaves + nested dataType attr_refs from a node's children.

        Handles every child kind a 3GPP attributes container can hold:
        - leaf / leaf-list -> Leaf on the class
        - list             -> a dataType class + an AttrRef
        - container        -> a single-instance structured attribute; its leaves
                              are flattened onto the class (not list-structured)
        - choice / case    -> attribute groupings; recurse and flatten leaves
                              (mutually-exclusive cardinality is not modelled here)
        Any other keyword is ignored but recorded in self.unhandled so a future
        schema shape cannot silently drop attributes.
        """
        for c in getattr(node, "i_children", []):
            if c.keyword in ("leaf", "leaf-list", "anydata", "anyxml"):
                # anydata/anyxml carry opaque, schema-less content; model them as
                # a property with no datatype (open range) rather than drop them.
                if c.arg != "idx":
                    cls.leaves.append(_leaf_from(c))
            elif c.keyword == "list":
                # A nested list that itself has an 'attributes' container is a
                # genuine IOC (register as such); otherwise it is a structured
                # dataType value. Either way it becomes an AttrRef target.
                # Use _class_identity to get the target IRI consistent with registration.
                if _is_ioc(c):
                    self.register_ioc(c)
                else:
                    self._register_datatype(c)
                # Get the consistent IRI via _class_identity
                _, _, target_iri = _class_identity(c, self.ctx)
                cls.attr_refs.append(AttrRef(
                    name=c.arg, target_iri=target_iri,
                    min_elements=_int(c, "min-elements"),
                    max_elements=_int(c, "max-elements"),
                    description=_desc(c),
                ))
            elif c.keyword in ("container", "choice", "case"):
                # structured attribute grouping — recurse, flatten its leaves
                self._fill_children(cls, c)
            else:
                self.unhandled.add(c.keyword)

    def register_ioc(self, list_node) -> Klass:
        name, ns, iri = _class_identity(list_node, self.ctx)
        existing = self.seen.get(iri)
        if existing is not None:
            if existing.kind == "ioc":
                return existing
            # Previously reached as a nested dataType, but it is a genuine IOC
            # (has an attributes container). Upgrade in place: set kind and add
            # IOC-only semantics (subclass_of, contains). Its leaves/attr_refs
            # were already populated by _register_datatype, so don't refill them.
            cls = existing
            cls.kind = "ioc"
            cls.subclass_of = _subclasses(list_node)
            self._fill_containment(cls, list_node)
            return cls
        cls = Klass(name=name, namespace=ns, kind="ioc",
                    description=_desc(list_node),
                    subclass_of=_subclasses(list_node))
        self.seen[iri] = cls
        self.model.classes.append(cls)

        # simple leaves directly on the list node (e.g. key 'id' is skipped as idx-like? no: keep non-idx)
        for c in getattr(list_node, "i_children", []):
            if c.keyword in ("leaf", "leaf-list") and c.arg != "idx":
                cls.leaves.append(_leaf_from(c))

        # attributes container: leaves + nested dataType structures
        attrs = _attributes_container(list_node)
        if attrs is not None:
            self._fill_children(cls, attrs)

        # sibling lists = contained sub-IOCs
        self._fill_containment(cls, list_node)
        return cls

    def _fill_containment(self, cls: Klass, list_node) -> None:
        """Record sibling lists that are themselves IOCs as contained sub-IOCs."""
        for c in getattr(list_node, "i_children", []):
            if c.keyword == "list" and c.arg != "idx" and _is_ioc(c):
                self.register_ioc(c)
                _, _, child_iri = _class_identity(c, self.ctx)
                if child_iri not in cls.contains:
                    cls.contains.append(child_iri)

    def run(self, ctx):
        self.ctx = ctx  # store for _class_identity resolver
        # Sort modules by key for deterministic iteration
        for key in sorted(ctx.modules.keys()):
            m = ctx.modules[key]
            if m.keyword != "module":
                continue
            # Capture revision metadata for versioning
            ns = _ns(m)
            if ns:
                rev = m.search_one("revision")
                if rev is not None:
                    date = rev.arg
                    ref_stmt = rev.search_one("reference")
                    cr_ref = ref_stmt.arg if ref_stmt is not None else None
                    self.model.revisions[ns] = (date, cr_ref)

            for td in m.search("typedef"):
                rt = resolve_type(td.search_one("type"))
                self.model.typedefs.append(
                    Typedef(td.arg, _ns(m), rt.enums, rt.pattern, _desc(td)))

        for key in sorted(ctx.modules.keys()):
            m = ctx.modules[key]
            if m.keyword != "module":
                continue
            for aug in m.search("augment"):
                tgt = getattr(aug, "i_target_node", None)
                if tgt is None or tgt.keyword != "list":
                    continue
                parent = self.register_ioc(tgt)
                for child in getattr(aug, "i_children", []):
                    if child.keyword == "list" and child.arg != "idx" and _is_ioc(child):
                        self.register_ioc(child)
                        _, _, ci = _class_identity(child, self.ctx)
                        if ci not in parent.contains:
                            parent.contains.append(ci)
        return self.model


def parse(yang_files, search_paths) -> tuple[Model, list[str]]:
    ctx, errors = build_context(yang_files, search_paths)
    parser = _Parser()
    model = parser.run(ctx)
    # Surface any attribute-child node kinds we did not model, so coverage gaps
    # are visible rather than silent.
    for kw in sorted(parser.unhandled):
        errors.append(f"unmodeled attribute node kind: {kw!r}")
    return model, errors
