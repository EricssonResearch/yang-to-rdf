"""Build an RDF-oriented IR from pyang's *resolved* schema tree."""
from __future__ import annotations

from dataclasses import dataclass, field

from yang_to_rdf.namespace import (
    DEFAULT_BASE_IRI,
    class_iri,
    module_iri,
    namespace_base,
    vocab_namespace,
)
from yang_to_rdf.pyang_context import build_context
from yang_to_rdf.type_resolver import resolve_type

INVARIANT_EXT = ("_3gpp-common-yang-extensions", "inVariant")
MANAGED_FUNCTION_GRP = "ManagedFunctionGrp"
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
    """An emitted RDF class. `kind` is "ioc" (a managed object, from a YANG list
    with an `attributes` container) or "datatype" (a 3GPP <<dataType>> structured
    attribute). Named `Klass` to avoid shadowing the `class` keyword. This is the
    central IR node the converters walk."""
    name: str
    namespace: str
    kind: str  # "ioc" | "datatype"
    description: str = ""
    subclass_of: list[str] = field(default_factory=list)   # parent class IRIs
    leaves: list[Leaf] = field(default_factory=list)        # scalar attributes
    attr_refs: list[AttrRef] = field(default_factory=list)  # nested dataType links
    contains: list[str] = field(default_factory=list)       # child IOC IRIs (nameContains)


@dataclass
class Typedef:
    name: str
    namespace: str
    enums: list[str] = field(default_factory=list)
    pattern: str | None = None
    description: str = ""


@dataclass
class ModuleMeta:
    """Module-level metadata lifted verbatim from the YANG module's own
    statements (organization/contact/description/reference), so ontology
    metadata is sourced from the input rather than invented. Any field may be
    empty when the module omits that statement."""
    name: str
    organization: str = ""
    contact: str = ""
    description: str = ""
    reference: str = ""
    # The module's own `prefix` statement (RFC 7950 §7.1.4). Used to bind a
    # readable Turtle prefix rather than inventing one. Measured on the 3GPP
    # Rel-19 set: 118 modules, 118 distinct prefixes, all NCName-legal.
    prefix: str = ""


@dataclass
class Model:
    classes: list[Klass] = field(default_factory=list)
    typedefs: list[Typedef] = field(default_factory=list)
    # Keyed by MODULE IRI (<base>yang/<module>), not by YANG namespace.
    revisions: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    # Every source module's ontology IRI. This is the authoritative set used to
    # partition output per module.
    module_iris: set[str] = field(default_factory=set)
    # Module IRI -> metadata from that module's YANG statements.
    module_meta: dict[str, "ModuleMeta"] = field(default_factory=dict)
    # Module IRI -> the module's YANG `namespace` statement, retained so the
    # mapping stays queryable and reversible (spec D6). Not merely decorative:
    # two modules in the 3GPP Rel-19 set have a namespace that disagrees with
    # their module name, so this is the only record of the original URN.
    module_yang_namespace: dict[str, str] = field(default_factory=dict)
    base_iri: str = DEFAULT_BASE_IRI

    @property
    def iocs(self) -> list[Klass]:
        return [c for c in self.classes if c.kind == "ioc"]


def _module_name(stmt) -> str:
    """The declared name of the module a statement belongs to.

    Submodules carry no `namespace`; they name their parent via `belongs-to`
    (RFC 7950 §7.2.2), and terms defined in a submodule belong to that parent.
    Resolving that here means every caller gets it, where previously only
    grouping resolution handled submodules.
    """
    m = stmt.i_module if getattr(stmt, "i_module", None) is not None else stmt
    if m.keyword == "submodule":
        bt = m.search_one("belongs-to")
        if bt is not None:
            return bt.arg
    return m.arg


def _yang_namespace(stmt) -> str:
    """The module's own `namespace` statement, retained for provenance only."""
    m = stmt.i_module if getattr(stmt, "i_module", None) is not None else stmt
    n = m.search_one("namespace")
    return n.arg if n is not None else ""


def _desc(stmt) -> str:
    d = stmt.search_one("description")
    return d.arg if d is not None else ""


def _stmt_arg(stmt, keyword) -> str:
    """Return a direct sub-statement's argument, or "" if absent."""
    s = stmt.search_one(keyword)
    return s.arg if s is not None else ""


def _int(stmt, kw) -> int | None:
    s = stmt.search_one(kw)
    if s is None:
        return None
    try:
        return int(s.arg)
    except (TypeError, ValueError):
        # pyang normally validates min/max-elements as integers; guard anyway so
        # a malformed value degrades to "unspecified" instead of crashing.
        return None


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


def _grouping_home_module(u):
    """Resolve the home module NAME for a uses statement's grouping.

    Returns a module name, not an IRI; the caller composes the IRI. Submodules
    are handled by _module_name via `belongs-to`.
    """
    g = getattr(u, "i_grouping", None)
    if g is None:
        return None
    m = getattr(g, "i_module", None)
    if m is None:
        return None
    return _module_name(m)


def _class_identity(list_node, ctx, base_iri):
    """Compute (name, module_iri, iri) identity for a list node's class.

    Design decision (see CONVERSION_NOTES.md §5): a class is identified by the
    YANG *grouping* it is built from, not the list node's own name. So a node
    `serviceProfileList` that `uses ServiceProfileGrp` becomes class
    `ServiceProfile` in the grouping's home module, and every node that reuses
    that grouping collapses to one shared class. This applies only when the node
    uses exactly one non-base grouping ending in 'Grp'; otherwise we fall back to
    node-based naming (name and namespace from the list node itself).
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
        home = _grouping_home_module(u)
        if home is not None:
            mod = module_iri(base_iri, home)
            return (class_name, mod, class_iri(namespace_base(mod), class_name))

    # Fallback: node-based naming
    mod = module_iri(base_iri, _module_name(list_node))
    name = list_node.arg
    return (name, mod, class_iri(namespace_base(mod), name))


def _leaf_from(stmt) -> Leaf:
    t = stmt.search_one("type")
    # anydata/anyxml have no 'type' and carry opaque content: leave xsd open.
    if t is None:
        return Leaf(
            name=stmt.arg,
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


def _subclasses(list_node, managed_function_iri: str) -> list[str]:
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
                    if managed_function_iri not in out:
                        out.append(managed_function_iri)
    return out


class _Parser:
    def __init__(self, base_iri: str = DEFAULT_BASE_IRI):
        self.base_iri = base_iri
        self.model = Model(base_iri=base_iri)
        self.managed_function_iri = str(vocab_namespace(base_iri).ManagedFunction)
        self.seen: dict[str, Klass] = {}
        # keywords encountered inside a class that we deliberately do not model,
        # collected so nothing is dropped silently (surfaced by parse()).
        self.unhandled: set[str] = set()
        self.ctx = None  # set in run()

    def _register_datatype(self, list_node) -> str:
        """Register a nested dataType list as a class; return its IRI."""
        name, ns, iri = _class_identity(list_node, self.ctx, self.base_iri)
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
                _, _, target_iri = _class_identity(c, self.ctx, self.base_iri)
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
        name, ns, iri = _class_identity(list_node, self.ctx, self.base_iri)
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
            cls.subclass_of = _subclasses(list_node, self.managed_function_iri)
            self._fill_containment(cls, list_node)
            return cls
        cls = Klass(name=name, namespace=ns, kind="ioc",
                    description=_desc(list_node),
                    subclass_of=_subclasses(list_node, self.managed_function_iri))
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
                _, _, child_iri = _class_identity(c, self.ctx, self.base_iri)
                if child_iri not in cls.contains:
                    cls.contains.append(child_iri)

    def run(self, ctx):
        self.ctx = ctx  # store for _class_identity resolver
        # Sort modules by key for deterministic iteration
        for key in sorted(ctx.modules.keys()):
            m = ctx.modules[key]
            if m.keyword != "module":
                continue
            # Module identity is the declared module name, so a module is
            # registered whether or not it declares a `namespace` — the old
            # namespace-keyed code silently skipped any module without one.
            mod = module_iri(self.base_iri, m.arg)
            self.model.module_iris.add(mod)
            ns = _yang_namespace(m)
            if ns:
                # Provenance only (spec D6): two modules in the 3GPP Rel-19 set
                # have a namespace that disagrees with their module name.
                self.model.module_yang_namespace[mod] = ns
            rev = m.search_one("revision")
            if rev is not None:
                date = rev.arg
                ref_stmt = rev.search_one("reference")
                cr_ref = ref_stmt.arg if ref_stmt is not None else None
                self.model.revisions[mod] = (date, cr_ref)
            # Capture module metadata (for ontology dcterms:* — sourced from
            # the YANG itself; any statement may be absent).
            self.model.module_meta[mod] = ModuleMeta(
                name=m.arg,
                organization=_stmt_arg(m, "organization"),
                contact=_stmt_arg(m, "contact"),
                description=_desc(m),
                reference=_stmt_arg(m, "reference"),
                prefix=_stmt_arg(m, "prefix"),
            )

            for td in m.search("typedef"):
                rt = resolve_type(td.search_one("type"))
                self.model.typedefs.append(
                    Typedef(td.arg, mod, rt.enums, rt.pattern, _desc(td)))

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
                        _, _, ci = _class_identity(child, self.ctx, self.base_iri)
                        if ci not in parent.contains:
                            parent.contains.append(ci)
        return self.model


def parse(yang_files, search_paths,
          base_iri: str = DEFAULT_BASE_IRI) -> tuple[Model, list[str]]:
    ctx, errors = build_context(yang_files, search_paths)
    parser = _Parser(base_iri)
    model = parser.run(ctx)
    # Surface any attribute-child node kinds we did not model, so coverage gaps
    # are visible rather than silent.
    for kw in sorted(parser.unhandled):
        errors.append(f"unmodeled attribute node kind: {kw!r}")
    return model, errors
