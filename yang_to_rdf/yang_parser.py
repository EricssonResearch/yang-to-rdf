"""Parse YANG modules using pyang into an intermediate representation."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyang.context import Context
from pyang.repository import FileRepository
from pyang.statements import Statement


@dataclass
class Leaf:
    name: str
    type_name: str  # e.g. "string", "uint32", "inet:ipv4-address", "enumeration"
    description: str = ""
    mandatory: bool = False
    is_list: bool = False  # True for leaf-list
    min_elements: int | None = None
    max_elements: int | None = None
    enums: list[str] = field(default_factory=list)
    pattern: str | None = None
    config: bool = True


@dataclass
class ListNode:
    """A YANG 'list' or 'container' inside a grouping."""
    name: str
    description: str = ""
    key: str | None = None
    min_elements: int | None = None
    max_elements: int | None = None
    leaves: list[Leaf] = field(default_factory=list)
    lists: list[ListNode] = field(default_factory=list)
    uses: list[str] = field(default_factory=list)


@dataclass
class Choice:
    name: str
    cases: dict[str, list[Leaf]] = field(default_factory=dict)  # case_name → leaves


@dataclass
class Grouping:
    name: str
    description: str = ""
    uses: list[str] = field(default_factory=list)  # referenced grouping names
    leaves: list[Leaf] = field(default_factory=list)
    leaf_lists: list[Leaf] = field(default_factory=list)
    lists: list[ListNode] = field(default_factory=list)
    choices: list[Choice] = field(default_factory=list)


@dataclass
class Augment:
    target_path: str  # e.g. "/me3gpp:ManagedElement"
    lists: list[ListNode] = field(default_factory=list)  # IOCs added


@dataclass
class Typedef:
    name: str
    base_type: str
    description: str = ""
    enums: list[str] = field(default_factory=list)
    pattern: str | None = None


@dataclass
class YangModule:
    name: str
    namespace: str
    prefix: str
    description: str = ""
    imports: dict[str, str] = field(default_factory=dict)  # prefix → module_name
    groupings: list[Grouping] = field(default_factory=list)
    typedefs: list[Typedef] = field(default_factory=list)
    augments: list[Augment] = field(default_factory=list)


def parse_yang_files(yang_files: list[str], search_paths: list[str]) -> tuple[list[YangModule], dict]:
    """Parse a set of YANG files and return their IR representations.

    Returns (modules, submodule_groupings) where submodule_groupings maps
    grouping name → Grouping for groupings defined in submodules.
    """
    repo = FileRepository(search_paths[0] if search_paths else ".", use_env=False)
    ctx = Context(repo)
    ctx.opts = _default_opts()

    # Add all search paths
    repo.dirs = list(search_paths)

    modules = []
    submodule_groupings: dict[str, Grouping] = {}
    for fpath in yang_files:
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
        ctx.add_module(fpath, text)

    # Validate (resolves imports, augments, uses)
    ctx.validate()

    for mod in ctx.modules.values():
        if mod.keyword in ("module", "submodule"):
            if mod.keyword == "submodule":
                # Index submodule groupings for cross-reference but don't emit as module
                _index_submodule_groupings(mod, submodule_groupings)
            else:
                parsed = _extract_module(mod)
                if parsed:
                    modules.append(parsed)

    return modules, submodule_groupings


def _index_submodule_groupings(stmt: Statement, index: dict) -> None:
    """Extract grouping names from a submodule for cross-reference."""
    for grp in stmt.search("grouping"):
        parsed = _extract_grouping(grp)
        index[parsed.name] = parsed
    for td in stmt.search("typedef"):
        parsed_td = _extract_typedef(td)
        index[f"typedef:{parsed_td.name}"] = parsed_td


def _extract_module(stmt: Statement) -> YangModule | None:
    """Extract IR from a parsed pyang module statement."""
    ns_stmt = stmt.search_one("namespace")
    prefix_stmt = stmt.search_one("prefix")

    if not ns_stmt:
        # Submodules don't have their own namespace — skip them.
        # Their content is included via the parent module's 'include'.
        return None

    namespace = ns_stmt.arg
    prefix = prefix_stmt.arg if prefix_stmt else ""
    desc_stmt = stmt.search_one("description")

    mod = YangModule(
        name=stmt.arg,
        namespace=namespace,
        prefix=prefix,
        description=desc_stmt.arg if desc_stmt else "",
    )

    # Imports
    for imp in stmt.search("import"):
        pfx = imp.search_one("prefix")
        if pfx:
            mod.imports[pfx.arg] = imp.arg

    # Groupings
    for grp in stmt.search("grouping"):
        mod.groupings.append(_extract_grouping(grp))

    # Typedefs
    for td in stmt.search("typedef"):
        mod.typedefs.append(_extract_typedef(td))

    # Augments
    for aug in stmt.search("augment"):
        mod.augments.append(_extract_augment(aug))

    return mod


def _extract_grouping(stmt: Statement) -> Grouping:
    desc = stmt.search_one("description")
    grp = Grouping(
        name=stmt.arg,
        description=desc.arg if desc else "",
    )
    for child in stmt.substmts:
        if child.keyword == "uses":
            grp.uses.append(child.arg)
        elif child.keyword == "leaf":
            grp.leaves.append(_extract_leaf(child))
        elif child.keyword == "leaf-list":
            grp.leaf_lists.append(_extract_leaf(child, is_list=True))
        elif child.keyword == "list":
            grp.lists.append(_extract_list_node(child))
        elif child.keyword == "choice":
            grp.choices.append(_extract_choice(child))
    return grp


def _extract_leaf(stmt: Statement, is_list: bool = False) -> Leaf:
    desc = stmt.search_one("description")
    mandatory = stmt.search_one("mandatory")
    type_stmt = stmt.search_one("type")
    config_stmt = stmt.search_one("config")
    min_el = stmt.search_one("min-elements")
    max_el = stmt.search_one("max-elements")

    type_name = type_stmt.arg if type_stmt else "string"
    enums = []
    pattern = None

    if type_stmt and type_name == "enumeration":
        enums = [e.arg for e in type_stmt.search("enum")]
    if type_stmt:
        pat = type_stmt.search_one("pattern")
        if pat:
            pattern = pat.arg

    return Leaf(
        name=stmt.arg,
        type_name=type_name,
        description=desc.arg if desc else "",
        mandatory=mandatory is not None and mandatory.arg == "true",
        is_list=is_list,
        min_elements=int(min_el.arg) if min_el else None,
        max_elements=int(max_el.arg) if max_el else None,
        enums=enums,
        pattern=pattern,
        config=config_stmt.arg != "false" if config_stmt else True,
    )


def _extract_list_node(stmt: Statement) -> ListNode:
    desc = stmt.search_one("description")
    key_stmt = stmt.search_one("key")
    min_el = stmt.search_one("min-elements")
    max_el = stmt.search_one("max-elements")

    node = ListNode(
        name=stmt.arg,
        description=desc.arg if desc else "",
        key=key_stmt.arg if key_stmt else None,
        min_elements=int(min_el.arg) if min_el else None,
        max_elements=int(max_el.arg) if max_el else None,
    )

    for child in stmt.substmts:
        if child.keyword == "leaf":
            node.leaves.append(_extract_leaf(child))
        elif child.keyword == "leaf-list":
            node.leaves.append(_extract_leaf(child, is_list=True))
        elif child.keyword == "list":
            node.lists.append(_extract_list_node(child))
        elif child.keyword == "uses":
            node.uses.append(child.arg)

    return node


def _extract_choice(stmt: Statement) -> Choice:
    choice = Choice(name=stmt.arg)
    for case_stmt in stmt.search("case"):
        leaves = []
        for child in case_stmt.substmts:
            if child.keyword in ("leaf", "leaf-list"):
                leaves.append(_extract_leaf(child, is_list=(child.keyword == "leaf-list")))
        choice.cases[case_stmt.arg] = leaves
    return choice


def _extract_typedef(stmt: Statement) -> Typedef:
    desc = stmt.search_one("description")
    type_stmt = stmt.search_one("type")
    type_name = type_stmt.arg if type_stmt else "string"
    enums = []
    pattern = None
    if type_stmt and type_name == "enumeration":
        enums = [e.arg for e in type_stmt.search("enum")]
    if type_stmt:
        pat = type_stmt.search_one("pattern")
        if pat:
            pattern = pat.arg
    return Typedef(
        name=stmt.arg,
        base_type=type_name,
        description=desc.arg if desc else "",
        enums=enums,
        pattern=pattern,
    )


def _extract_augment(stmt: Statement) -> Augment:
    aug = Augment(target_path=stmt.arg)
    for child in stmt.substmts:
        if child.keyword == "list":
            aug.lists.append(_extract_list_node(child))
    return aug


class _Opts:
    """Minimal options object for pyang Context."""
    def __init__(self):
        self.verbose = False
        self.debug = False
        self.canonical = False
        self.max_line_len = 0
        self.max_identifier_len = 0
        self.trim_yin_comments = False
        self.lax_xpath_checks = True
        self.strict = False
        self.list_errors = False
        self.ignore_errors = True
        self.ignore_error_tags = []
        self.keep_comments = False
        self.features = []
        self.deviations = []
        self.path = []


def _default_opts() -> _Opts:
    return _Opts()
