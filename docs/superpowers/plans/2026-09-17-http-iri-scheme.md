# HTTP IRI Scheme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the URN term IRIs with `https` hash-namespace IRIs under a configurable base, held in place by gates that run over the real corpus, and verifiable end-to-end by a third party in a container.

**Architecture:** All IRI construction already funnels through `yang_to_rdf/namespace.py`, and `output_writer.split_graph()` already partitions by prefix-matching whatever namespaces the parser reports. So the change is: teach `namespace.py` the new scheme plus validation, change what the parser *reports* as a module's namespace (a module-name-derived HTTP IRI rather than the YANG URN), and let the existing machinery follow. New surfaces are a `--base-iri` flag, a census/gate script, and a container.

**Tech Stack:** Python ≥3.10, `uv` (lockfile-driven), `pyang` ≥2.6, `rdflib` ≥7.0, `pytest` ≥9.1.1, Docker (`python:3.12-slim`).

**Spec:** `docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md` — read it first; this plan argues from it.

## Global Constraints

- Default base IRI: `https://semantics.ericsson.com/` — copied verbatim; it is the default, not a fallback. **No flag restores URN IRIs.**
- Scope separator between class and property local name: `.` (a single ASCII full stop).
- Minted vocabulary prefix: `y2r:`, namespace `<base>vocab#`. The old `nrm:` prefix and `https://3gpp.org/nrm/vocab#` namespace must not survive anywhere.
- Pinned example input: forge tag `Tag_Rel19_SA112`, commit `24ffa42e`, `--ref-type tags`.
- Target version: `0.3.0` (in `pyproject.toml`, `main.py --version`, `CHANGELOG.md`).
- **Never retype an IRI literal in a test.** 31 hardcoded IRIs exist today across 7 test files (`tests/test_rdf_converter.py`, `test_output_writer.py`, `test_shacl_converter.py`, `test_build_docs.py`, `test_reference_layer.py`, `test_versioning.py`) and `scripts/build_docs.py:10`. Each must be **derived** by calling the `namespace.py` helpers, not rewritten with the new base. A retyped literal is a copy, and copies drift.
- `quote()` is removed from term-IRI construction (percent-encoding is not NCName-legal — we validate and refuse instead). `quote()` is **retained** for the release label in `version_iri()`, which is a path segment, not an NCName.
- Every gate prints the size of the set it searched alongside its result. "0 violations out of 8,171 terms" is a finding; "0 violations" is not.
- Run only the tests covering what you changed; the full suite runs at task end before each commit.

---

### Task 1: The IRI vocabulary and its validation

`namespace.py` becomes the single place that knows the scheme. Pure functions, no YANG needed, so this task is fully testable on its own and every later task consumes it.

**Files:**
- Modify: `yang_to_rdf/namespace.py` (whole file, currently 40 lines)
- Test: `tests/test_namespace.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  ```python
  DEFAULT_BASE_IRI: str = "https://semantics.ericsson.com/"
  SCOPE_SEPARATOR: str = "."
  NCNAME_RE: re.Pattern           # anchored
  YANG_IDENTIFIER_RE: re.Pattern  # anchored

  def normalize_base_iri(base: str) -> str
  def vocab_namespace(base: str) -> rdflib.Namespace       # <base>vocab#
  def aggregate_ontology_iri(base: str) -> str            # <base>ontology
  def version_iri(base: str, label: str) -> str           # <base>ontology/version/<label>
  def module_iri(base: str, module_name: str) -> str      # <base>yang/<module>
  def shapes_module_iri(base: str, module_name: str) -> str  # <base>shapes/<module>
  def namespace_base(module_iri: str) -> str              # module_iri + "#"
  def class_iri(base: str, class_name: str) -> str
  def property_iri(base: str, class_name: str, prop_name: str) -> str
  def shape_iri(shapes_base: str, class_name: str) -> str
  def module_stem(module_iri: str) -> str                 # last "/" segment
  def bind_standard_namespaces(graph: rdflib.Graph, base: str) -> None
  ```
  `namespace_base`, `class_iri`, `property_iri`, `module_stem` keep their existing names and call shapes so downstream call sites change minimally. `NRM` is **deleted**; use `vocab_namespace(base)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_namespace.py`:

```python
"""The IRI scheme and its validation.

Scheme: docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md §4.
NCName is the production from XML Namespaces (W3C Recommendation, 8 Dec 2009);
the YANG identifier grammar is RFC 7950 §6.2.
"""
import pytest
from rdflib import Graph

from yang_to_rdf.namespace import (
    DEFAULT_BASE_IRI, SCOPE_SEPARATOR, NCNAME_RE,
    aggregate_ontology_iri, bind_standard_namespaces, class_iri, module_iri,
    module_stem, namespace_base, normalize_base_iri, property_iri, shape_iri,
    shapes_module_iri, version_iri, vocab_namespace,
)

BASE = DEFAULT_BASE_IRI
MOD = "_3gpp-5gc-nrm-amffunction"


def test_default_base_is_the_proposed_scheme():
    assert DEFAULT_BASE_IRI == "https://semantics.ericsson.com/"


def test_module_and_term_iris():
    m = module_iri(BASE, MOD)
    assert m == "https://semantics.ericsson.com/yang/_3gpp-5gc-nrm-amffunction"
    nb = namespace_base(m)
    assert nb == m + "#"
    assert class_iri(nb, "AMFFunction") == m + "#AMFFunction"
    assert property_iri(nb, "AMFFunction", "pLMNId") == m + "#AMFFunction.pLMNId"


def test_shapes_live_in_a_separate_namespace():
    """A class named FooShape must not collide with the shape of Foo (spec §4)."""
    nb = namespace_base(module_iri(BASE, MOD))
    sb = namespace_base(shapes_module_iri(BASE, MOD))
    assert class_iri(nb, "FooShape") != shape_iri(sb, "Foo")


def test_vocab_aggregate_and_version_iris():
    assert str(vocab_namespace(BASE)) == "https://semantics.ericsson.com/vocab#"
    assert str(vocab_namespace(BASE).nameContains) == \
        "https://semantics.ericsson.com/vocab#nameContains"
    assert aggregate_ontology_iri(BASE) == "https://semantics.ericsson.com/ontology"
    assert version_iri(BASE, "Rel-19") == \
        "https://semantics.ericsson.com/ontology/version/Rel-19"


def test_version_label_is_percent_encoded_because_it_is_a_path_segment():
    """Release labels are user-supplied path segments, not NCNames (spec §5)."""
    assert version_iri(BASE, "Rel 19/x") == \
        "https://semantics.ericsson.com/ontology/version/Rel%2019%2Fx"


def test_module_stem_round_trips():
    assert module_stem(module_iri(BASE, MOD)) == MOD
    assert module_stem(shapes_module_iri(BASE, MOD)) == MOD


@pytest.mark.parametrize("base,expected", [
    ("https://example.org/x", "https://example.org/x/"),
    ("https://example.org/x/", "https://example.org/x/"),
    ("http://example.org/", "http://example.org/"),
])
def test_normalize_base_iri_adds_one_trailing_slash(base, expected):
    assert normalize_base_iri(base) == expected


@pytest.mark.parametrize("bad", [
    "yang/rel19",                 # relative
    "urn:3gpp:sa5:x",             # not http(s)
    "ftp://example.org/",         # wrong scheme
    "https:///nohost",            # empty authority
    "",
])
def test_normalize_base_iri_refuses_non_http_bases(bad):
    with pytest.raises(ValueError, match="RFC 3986"):
        normalize_base_iri(bad)


# --- G5: YANG identifier validation --------------------------------------
# Cannot be reached by real 3GPP YANG (all 2,014 local names are alphanumeric),
# so it is exercised only by these constructed inputs.

@pytest.mark.parametrize("bad", ["1leading", "-leading", ".leading", "has space",
                                 "has/slash", "has:colon", ""])
def test_class_iri_refuses_non_yang_identifiers(bad):
    with pytest.raises(ValueError, match="RFC 7950"):
        class_iri(namespace_base(module_iri(BASE, MOD)), bad)


# --- G9: the '.' separator must stay unambiguous -------------------------
# Also unreachable on the real corpus: 0 of 1,482 local names contain a dot.

def test_class_name_containing_the_separator_is_refused():
    nb = namespace_base(module_iri(BASE, MOD))
    with pytest.raises(ValueError, match=r"separator"):
        class_iri(nb, "Foo.Bar")


def test_property_name_containing_the_separator_is_refused():
    nb = namespace_base(module_iri(BASE, MOD))
    with pytest.raises(ValueError, match=r"separator"):
        property_iri(nb, "Foo", "bar.baz")


def test_separator_rejection_is_what_prevents_ambiguity():
    """Without G9, class 'A.B' and property 'B' of class 'A' would collide.
    Documents the collision the guard exists to prevent."""
    nb = namespace_base(module_iri(BASE, MOD))
    assert class_iri(nb, "AB") != property_iri(nb, "A", "B")
    for name in ("A.B",):
        with pytest.raises(ValueError):
            class_iri(nb, name)


# --- G8: NCName legality -------------------------------------------------

@pytest.mark.parametrize("ok", ["A", "_", "_3gpp", "a.b", "a-b", "a_b", "X1"])
def test_ncname_regex_accepts_legal_names(ok):
    assert NCNAME_RE.match(ok)


@pytest.mark.parametrize("bad", ["1a", "-a", ".a", "a/b", "a:b", "a b", ""])
def test_ncname_regex_rejects_illegal_names(bad):
    assert not NCNAME_RE.match(bad)


def test_bound_prefixes_include_y2r_and_not_nrm():
    g = Graph()
    bind_standard_namespaces(g, BASE)
    bound = {p: str(n) for p, n in g.namespaces()}
    assert bound["y2r"] == "https://semantics.ericsson.com/vocab#"
    assert "nrm" not in bound
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_namespace.py -q`
Expected: collection error — `ImportError: cannot import name 'DEFAULT_BASE_IRI'`.

- [ ] **Step 3: Rewrite `yang_to_rdf/namespace.py`**

```python
"""IRI construction and shared graph setup for the RDF converters.

Scheme (docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md §4):

    <base>vocab#<term>                    minted vocabulary        prefix y2r:
    <base>ontology                        aggregate ontology
    <base>ontology/version/<label>        owl:versionIRI
    <base>yang/<module>                   per-module ontology
    <base>yang/<module>#<Class>           class / typedef
    <base>yang/<module>#<Class>.<prop>    property, class-scoped
    <base>shapes/<module>#<Class>         SHACL NodeShape

Each module gets a *hash namespace* so that every local name is a legal NCName
(XML Namespaces, W3C Recommendation 8 Dec 2009) and a module's terms share one
namespace -- which the two-level slash form this replaces did not achieve.
Hash over slash follows the size criterion in "Best Practice Recipes for
Publishing RDF Vocabularies" (W3C *Working Group Note*, 28 Aug 2008 -- guidance,
not a Recommendation): median 70 terms and at most 256 per module puts this in
its "single Web access" case, so serving it needs only static files.

The default base names an Ericsson-owned namespace that is NOT currently
dereferenceable (semantics.ericsson.com had no DNS record as of 2026-09-17).
Terms under it are minted by this project and assert no 3GPP endorsement.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

from rdflib import Graph, Namespace
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, XSD

# Ericsson-owned, ours, not currently dereferenceable. See module docstring.
DEFAULT_BASE_IRI = "https://semantics.ericsson.com/"

# Joins a class and property local name: <Class>.<prop>. OURS -- no standard
# prescribes it. It is legal in a non-initial NCName position, and it is already
# this project's convention for rdfs:label (6,142 property labels use it). No
# ASCII separator can be unambiguous, because RFC 7950 identifiers and NCNames
# permit the same character set -- so identifiers containing it are REFUSED
# rather than silently made ambiguous. See spec §3.
SCOPE_SEPARATOR = "."

# NCName restricted to the ASCII range, which is all RFC 7950 identifiers can
# contain. XML Namespaces defines NCName as an XML Name minus ':', so '/' is
# excluded by construction and the first character cannot be a digit, '-' or '.'.
NCNAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*\Z")

# RFC 7950 §6.2: identifier = (ALPHA / "_") *(ALPHA / DIGIT / "_" / "-" / ".")
YANG_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*\Z")


def normalize_base_iri(base: str) -> str:
    """Validate a base IRI and guarantee exactly one trailing '/'."""
    parts = urlsplit(base or "")
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(
            f"--base-iri must be an absolute http(s) IRI with an authority "
            f"(RFC 3986 §3): got {base!r}"
        )
    return base if base.endswith("/") else base + "/"


def _check_identifier(name: str, what: str) -> str:
    """Refuse anything that cannot become an unambiguous NCName local part."""
    if not YANG_IDENTIFIER_RE.match(name or ""):
        raise ValueError(
            f"{what} {name!r} is not a valid YANG identifier (RFC 7950 §6.2), "
            f"so it cannot form a legal NCName local part "
            f"(XML Namespaces, W3C Recommendation)"
        )
    if SCOPE_SEPARATOR in name:
        raise ValueError(
            f"{what} {name!r} contains {SCOPE_SEPARATOR!r}, which this project "
            f"reserves as the class/property scope separator. No ASCII separator "
            f"can be unambiguous here (RFC 7950 identifiers and NCNames share a "
            f"character set), so such names are refused rather than made "
            f"ambiguous. See the IRI scheme design, §3."
        )
    return name


def vocab_namespace(base: str) -> Namespace:
    """The project's minted vocabulary. The entire non-standard term surface."""
    return Namespace(f"{base}vocab#")


def aggregate_ontology_iri(base: str) -> str:
    return f"{base}ontology"


def version_iri(base: str, label: str) -> str:
    """owl:versionIRI. The label is a user-supplied *path segment*, not an
    NCName, so percent-encoding is correct here (unlike term local names)."""
    return f"{base}ontology/version/{quote(label, safe='')}"


def module_iri(base: str, module_name: str) -> str:
    return f"{base}yang/{_check_identifier(module_name, 'module name')}"


def shapes_module_iri(base: str, module_name: str) -> str:
    return f"{base}shapes/{_check_identifier(module_name, 'module name')}"


def namespace_base(module_iri_: str) -> str:
    """The hash namespace for a module (or shapes) ontology IRI."""
    return module_iri_ + "#"


def class_iri(base: str, class_name: str) -> str:
    return f"{base}{_check_identifier(class_name, 'class name')}"


def property_iri(base: str, class_name: str, prop_name: str) -> str:
    return (f"{base}{_check_identifier(class_name, 'class name')}"
            f"{SCOPE_SEPARATOR}{_check_identifier(prop_name, 'property name')}")


def shape_iri(shapes_base: str, class_name: str) -> str:
    return f"{shapes_base}{_check_identifier(class_name, 'class name')}"


def module_stem(module_iri_: str) -> str:
    """Filename stem for a module IRI: the declared YANG module name."""
    return module_iri_.rsplit("/", 1)[-1]


def bind_standard_namespaces(graph: Graph, base: str) -> None:
    """Bind the prefixes every converter uses, so serialized TTL is readable."""
    for prefix, ns in (("rdf", RDF), ("rdfs", RDFS), ("owl", OWL),
                       ("xsd", XSD), ("y2r", vocab_namespace(base)),
                       ("dcterms", DCTERMS)):
        graph.bind(prefix, ns)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_namespace.py -q`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/namespace.py tests/test_namespace.py
git commit -S -m "Add HTTP hash-namespace IRI vocabulary with NCName validation

Replaces the URN-derived helpers. Term local names are validated as RFC 7950
identifiers and refused if they contain the '.' scope separator, since no ASCII
separator can be unambiguous. quote() is dropped from term construction
(percent-encoding is not NCName-legal) and retained only for the version label,
which is a path segment.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Module identity from the declared module name

The parser currently reports each module's YANG `namespace` URN as the key. It reports the module IRI instead, and keeps the URN as provenance.

**Files:**
- Modify: `yang_to_rdf/yang_parser.py` — `MANAGED_FUNCTION_IRI` (line 12), `Model` (85–99), `_ns` (102–105), `_grouping_home_ns` (149–165), `_class_identity` (168–206), `_Parser.__init__` (267–274), `_Parser.run` (374–421), `parse` (424–432)
- Test: `tests/test_yang_parser.py` (extend), `tests/test_namespace.py` (unchanged)

**Interfaces:**
- Consumes: Task 1's `module_iri`, `namespace_base`, `class_iri`, `vocab_namespace`, `DEFAULT_BASE_IRI`.
- Produces:
  ```python
  def parse(yang_files, search_paths, base_iri: str = DEFAULT_BASE_IRI) -> tuple[Model, list[str]]

  @dataclass
  class Model:
      classes: list[Klass]
      typedefs: list[Typedef]
      revisions: dict[str, tuple[str, str | None]]   # keyed by MODULE IRI
      module_iris: set[str]                            # renamed from module_namespaces
      module_meta: dict[str, ModuleMeta]               # keyed by MODULE IRI
      module_yang_namespace: dict[str, str]            # module IRI -> YANG namespace URN
      base_iri: str
  ```
  `Klass.namespace` and `Typedef.namespace` now hold the **module IRI** (`<base>yang/<mod>`, no `#`). Field names unchanged so converter call sites keep working.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_yang_parser.py`:

```python
from yang_to_rdf.namespace import DEFAULT_BASE_IRI, module_iri


def test_module_identity_is_the_declared_module_name(parsed_model):
    """Keying on the module name, not the YANG namespace, corrects two real
    upstream discrepancies (spec §4). Both are asserted, not assumed."""
    model, _ = parsed_model
    typo = module_iri(DEFAULT_BASE_IRI, "_3gpp-5gc-nrm-externalseppfunction")
    sector = module_iri(DEFAULT_BASE_IRI, "_3gpp-nr-nrm-nrsectorcarrier")
    assert typo in model.module_iris, "module name should win over the typo'd namespace"
    assert sector in model.module_iris
    assert not any("extternal" in m for m in model.module_iris)
    assert not any("nrnetwork-nrsectorcarrier" in m for m in model.module_iris)


def test_yang_namespace_urns_are_retained_as_provenance(parsed_model):
    model, _ = parsed_model
    assert len(model.module_yang_namespace) == len(model.module_iris)
    typo = module_iri(DEFAULT_BASE_IRI, "_3gpp-5gc-nrm-externalseppfunction")
    assert model.module_yang_namespace[typo] == \
        "urn:3gpp:sa5:_3gpp-5gc-nrm-extternalseppfunction"


def test_no_urn_survives_in_class_or_property_namespaces(parsed_model):
    model, _ = parsed_model
    offenders = [c.namespace for c in model.classes if c.namespace.startswith("urn:")]
    assert not offenders, f"{len(offenders)} of {len(model.classes)} classes kept a URN"


def test_every_class_namespace_is_a_known_module_iri(parsed_model):
    model, _ = parsed_model
    unknown = {c.namespace for c in model.classes} - model.module_iris
    assert not unknown, f"{len(unknown)} class namespaces are not module IRIs: {sorted(unknown)[:3]}"


def test_submodule_classes_resolve_to_their_parent_module(parsed_model):
    """The 2 submodules in this set have no `namespace`; their groupings must
    resolve through `belongs-to` (RFC 7950 §7.2.2) to the parent module."""
    model, _ = parsed_model
    names = {c.name: c.namespace for c in model.classes}
    assert names["ServiceProfile"] == module_iri(DEFAULT_BASE_IRI, "_3gpp-ns-nrm-networkslice")
    assert names["SliceProfile"] == module_iri(
        DEFAULT_BASE_IRI, "_3gpp-ns-nrm-networkslicesubnet")


def test_base_iri_is_threaded_through_parse(yang_dir, external_yams_dir):
    import glob, os
    from yang_to_rdf.yang_parser import parse
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp-common-top.yang")))
    model, _ = parse(files, [yang_dir, external_yams_dir],
                     base_iri="https://example.org/x/")
    assert model.base_iri == "https://example.org/x/"
    assert all(m.startswith("https://example.org/x/yang/") for m in model.module_iris)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_yang_parser.py -q`
Expected: FAIL — `AttributeError: 'Model' object has no attribute 'module_iris'`. (If the whole file skips, the dataset is missing: set `YANG_TEST_ZIP` to a copy of `MnS-Rel-19-yang-models.zip`. A skip is not a pass.)

- [ ] **Step 3: Implement**

In `yang_to_rdf/yang_parser.py`:

Replace the import and the `MANAGED_FUNCTION_IRI` constant:

```python
from yang_to_rdf.namespace import (
    DEFAULT_BASE_IRI, class_iri, module_iri, namespace_base, vocab_namespace,
)
```

Delete the `MANAGED_FUNCTION_IRI = "https://3gpp.org/nrm/vocab#ManagedFunction"` line; it becomes base-dependent, so it is computed per parse.

Extend `Model`:

```python
@dataclass
class Model:
    classes: list[Klass] = field(default_factory=list)
    typedefs: list[Typedef] = field(default_factory=list)
    # Keyed by MODULE IRI (<base>yang/<module>), not by YANG namespace.
    revisions: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    # Every source module's ontology IRI. The authoritative set used to
    # partition output per module.
    module_iris: set[str] = field(default_factory=set)
    module_meta: dict[str, "ModuleMeta"] = field(default_factory=dict)
    # Module IRI -> the module's YANG `namespace` statement, retained so the
    # mapping stays queryable and reversible (spec D6). Two modules in the 3GPP
    # Rel-19 set have a namespace that does not match their module name.
    module_yang_namespace: dict[str, str] = field(default_factory=dict)
    base_iri: str = DEFAULT_BASE_IRI

    @property
    def iocs(self) -> list[Klass]:
        return [c for c in self.classes if c.kind == "ioc"]
```

Replace `_ns` with a module-name resolver that handles submodules uniformly (the
old `_ns` returned `""` for a submodule; only `_grouping_home_ns` handled
`belongs-to`):

```python
def _module_name(stmt, ctx) -> str:
    """The declared name of the module a statement belongs to.

    Submodules carry no `namespace`; they name their parent via `belongs-to`
    (RFC 7950 §7.2.2), and terms defined in a submodule belong to that parent.
    """
    m = stmt.i_module if getattr(stmt, "i_module", None) is not None else stmt
    if m.keyword == "submodule":
        bt = m.search_one("belongs-to")
        if bt is not None:
            return bt.arg
    return m.arg


def _yang_namespace(stmt) -> str:
    """The module's own `namespace` statement, for provenance only."""
    m = stmt.i_module if getattr(stmt, "i_module", None) is not None else stmt
    n = m.search_one("namespace")
    return n.arg if n is not None else ""
```

`_grouping_home_ns` becomes name-based and loses its `ctx.get_module` lookup:

```python
def _grouping_home_ns(u, ctx):
    """Resolve the module IRI for a uses statement's grouping."""
    g = getattr(u, "i_grouping", None)
    if g is None:
        return None
    m = getattr(g, "i_module", None)
    if m is None:
        return None
    return _module_name(m, ctx)
```

Note this now returns a **module name**, and `_class_identity` turns it into an IRI. Update `_class_identity` to take the base and build IRIs through Task 1's helpers:

```python
def _class_identity(list_node, ctx, base_iri):
    """Compute (name, module_iri, iri) identity for a list node's class.

    Design decision (see CONVERSION_NOTES.md §5): a class is identified by the
    YANG *grouping* it is built from, not the list node's own name. ...
    (keep the rest of the existing docstring verbatim)
    """
    uses_stmts = [s for s in list_node.substmts if s.keyword == "uses"]

    real_groupings = []
    for u in uses_stmts:
        g = getattr(u, "i_grouping", None)
        if g is None:
            continue
        local_name = g.arg.split(":")[-1]
        if local_name not in BASE_GROUPINGS and local_name.endswith("Grp"):
            real_groupings.append((u, local_name))

    if len(real_groupings) == 1:
        u, local_name = real_groupings[0]
        class_name = local_name[:-3]
        home = _grouping_home_ns(u, ctx)
        if home is not None:
            mod = module_iri(base_iri, home)
            return (class_name, mod, class_iri(namespace_base(mod), class_name))

    mod = module_iri(base_iri, _module_name(list_node, ctx))
    name = list_node.arg
    return (name, mod, class_iri(namespace_base(mod), name))
```

Thread the base through `_Parser`. In `__init__`:

```python
    def __init__(self, base_iri: str = DEFAULT_BASE_IRI):
        self.base_iri = base_iri
        self.model = Model(base_iri=base_iri)
        self.managed_function_iri = str(vocab_namespace(base_iri).ManagedFunction)
        self.seen: dict[str, Klass] = {}
        self.unhandled: set[str] = set()
        self.ctx = None
```

`_subclasses` currently reads the module-level `MANAGED_FUNCTION_IRI`; make it a
method parameter. At its two call sites (`register_ioc`, line 342 and 347) pass
`self.managed_function_iri`, and change the function signature to
`_subclasses(list_node, managed_function_iri)`, replacing both uses of the old
constant inside it (lines 262–263) with the parameter.

Every `_class_identity(x, self.ctx)` call becomes
`_class_identity(x, self.ctx, self.base_iri)` — there are five, at lines 278,
317, 331, 370 and 418.

In `run()`, replace the metadata block:

```python
            ns = _yang_namespace(m)
            mod = module_iri(self.base_iri, m.arg)
            self.model.module_iris.add(mod)
            if ns:
                self.model.module_yang_namespace[mod] = ns
            rev = m.search_one("revision")
            if rev is not None:
                date = rev.arg
                ref_stmt = rev.search_one("reference")
                cr_ref = ref_stmt.arg if ref_stmt is not None else None
                self.model.revisions[mod] = (date, cr_ref)
            self.model.module_meta[mod] = ModuleMeta(
                name=m.arg,
                organization=_stmt_arg(m, "organization"),
                contact=_stmt_arg(m, "contact"),
                description=_desc(m),
                reference=_stmt_arg(m, "reference"),
            )

            for td in m.search("typedef"):
                rt = resolve_type(td.search_one("type"))
                self.model.typedefs.append(
                    Typedef(td.arg, mod, rt.enums, rt.pattern, _desc(td)))
```

Note the `if ns:` guard now wraps only the provenance line — a module is
registered whether or not it declares a namespace, which the old code did not do.

Finally:

```python
def parse(yang_files, search_paths, base_iri: str = DEFAULT_BASE_IRI) -> tuple[Model, list[str]]:
    ctx, errors = build_context(yang_files, search_paths)
    parser = _Parser(base_iri)
    model = parser.run(ctx)
    for kw in sorted(parser.unhandled):
        errors.append(f"unmodeled attribute node kind: {kw!r}")
    return model, errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_yang_parser.py tests/test_namespace.py -q`
Expected: PASS. Other test files still fail (they assert URN IRIs) — Task 4 fixes them.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/yang_parser.py tests/test_yang_parser.py
git commit -S -m "Key module identity on the declared module name

The parser reports <base>yang/<module> instead of the YANG namespace URN, and
retains the URN in Model.module_yang_namespace. Corrects two upstream
discrepancies in this module set: a typo'd namespace and one namespace that
names a different module than its file. Submodules now resolve through
belongs-to uniformly, where previously only grouping resolution did.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Partition, filenames, provenance and prefixes

**Files:**
- Modify: `yang_to_rdf/output_writer.py` (whole file, 186 lines)
- Test: `tests/test_output_writer.py`, `tests/test_versioning.py`

**Interfaces:**
- Consumes: Task 1's helpers; Task 2's `Model.module_iris`, `.module_yang_namespace`, `.base_iri`.
- Produces:
  ```python
  def module_prefix_map(base: str, module_iris: set[str]) -> dict[str, str]
  def module_ns(iri, prefix_map: dict[str, str]) -> str | None
  def split_graph(g: Graph, prefix_map: dict[str, str]) -> tuple[dict[str, Graph], Graph]
  def stamp_versions(graph: Graph, model, release_label: str | None = None,
                     aggregate: bool = False) -> None
  def module_stem(module_iri: str) -> str   # re-exported from namespace.py
  ```
  `split_graph` returns modules keyed by **module IRI**. `INDEX_ONTOLOGY` the constant is deleted; the aggregate IRI comes from `aggregate_ontology_iri(model.base_iri)`.

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/test_output_writer.py` so every IRI is **derived**:

```python
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from yang_to_rdf.namespace import (
    DEFAULT_BASE_IRI, class_iri, module_iri, namespace_base, property_iri,
    shape_iri, shapes_module_iri, vocab_namespace,
)
from yang_to_rdf.output_writer import module_ns, module_prefix_map, split_graph

BASE = DEFAULT_BASE_IRI
MOD_A = module_iri(BASE, "_3gpp-5gc-nrm-amffunction")
MOD_B = module_iri(BASE, "_3gpp-common-managed-element")
PMAP = module_prefix_map(BASE, {MOD_A, MOD_B})


def test_module_ns_matches_the_ontology_iri_itself():
    assert module_ns(URIRef(MOD_A), PMAP) == MOD_A


def test_module_ns_matches_hash_terms():
    t = class_iri(namespace_base(MOD_A), "AMFFunction")
    p = property_iri(namespace_base(MOD_A), "AMFFunction", "pLMNId")
    assert module_ns(URIRef(t), PMAP) == MOD_A
    assert module_ns(URIRef(p), PMAP) == MOD_A


def test_shape_iris_route_to_the_owning_module():
    """Shapes live in <base>shapes/<mod>#, a different prefix, but must land in
    the same module's file (spec §4)."""
    s = shape_iri(namespace_base(shapes_module_iri(BASE, "_3gpp-5gc-nrm-amffunction")),
                  "AMFFunction")
    assert module_ns(URIRef(s), PMAP) == MOD_A


def test_minted_vocabulary_belongs_to_no_module():
    assert module_ns(URIRef(str(vocab_namespace(BASE).nameContains)), PMAP) is None


def test_a_module_iri_that_prefixes_another_does_not_steal_its_terms():
    """'<base>yang/mod' must not capture '<base>yang/mod-extra#X'."""
    short = module_iri(BASE, "mod")
    long_ = module_iri(BASE, "mod-extra")
    pmap = module_prefix_map(BASE, {short, long_})
    t = class_iri(namespace_base(long_), "X")
    assert module_ns(URIRef(t), pmap) == long_


def test_split_graph_routes_terms_shapes_and_vocab():
    g = Graph()
    cls = URIRef(class_iri(namespace_base(MOD_A), "AMFFunction"))
    shp = URIRef(shape_iri(
        namespace_base(shapes_module_iri(BASE, "_3gpp-5gc-nrm-amffunction")),
        "AMFFunction"))
    voc = URIRef(str(vocab_namespace(BASE).nameContains))
    g.add((cls, RDF.type, RDFS.Class))
    g.add((shp, RDF.type, RDFS.Resource))
    g.add((voc, RDF.type, OWL.ObjectProperty))
    mods, index = split_graph(g, PMAP)
    assert set(mods) == {MOD_A}
    assert (cls, RDF.type, RDFS.Class) in mods[MOD_A]
    assert (shp, RDF.type, RDFS.Resource) in mods[MOD_A]
    assert (voc, RDF.type, OWL.ObjectProperty) in index
    assert (URIRef(MOD_A), RDF.type, OWL.Ontology) in mods[MOD_A]


def test_split_graph_drops_no_triple():
    g = Graph()
    g.add((URIRef("https://example.org/orphan"), RDF.type, RDFS.Class))
    mods, index = split_graph(g, PMAP)
    total = len(index) + sum(len(m) for m in mods.values())
    assert total >= len(g), f"{len(g)} in, {total} out"
```

Add to `tests/test_versioning.py` (and replace its hardcoded URNs with
`module_iri(DEFAULT_BASE_IRI, "…")` calls throughout, including the synthetic
`_3gpp-5gc-nrm-aaa`/`bbb`/`ccc`/`present`/`absent` fixtures):

```python
def test_module_ontology_carries_yang_provenance(parsed_model):
    """D6: the discarded YANG namespace stays queryable."""
    from yang_to_rdf.namespace import (
        DEFAULT_BASE_IRI, module_iri, vocab_namespace)
    from yang_to_rdf.output_writer import stamp_versions
    model, _ = parsed_model
    y2r = vocab_namespace(DEFAULT_BASE_IRI)
    mod = module_iri(DEFAULT_BASE_IRI, "_3gpp-5gc-nrm-externalseppfunction")
    g = Graph()
    g.add((URIRef(class_iri(namespace_base(mod), "SEPPFunction")), RDF.type, RDFS.Class))
    stamp_versions(g, model)
    assert (URIRef(mod), y2r.yangModuleName,
            Literal("_3gpp-5gc-nrm-externalseppfunction")) in g
    assert (URIRef(mod), y2r.yangNamespace,
            URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-extternalseppfunction")) in g


def test_version_iri_uses_the_configured_base(parsed_model):
    from yang_to_rdf.namespace import DEFAULT_BASE_IRI, aggregate_ontology_iri, version_iri
    from yang_to_rdf.output_writer import stamp_versions
    model, _ = parsed_model
    g = Graph()
    stamp_versions(g, model, release_label="Rel-19", aggregate=True)
    agg = URIRef(aggregate_ontology_iri(DEFAULT_BASE_IRI))
    assert (agg, OWL.versionIRI, URIRef(version_iri(DEFAULT_BASE_IRI, "Rel-19"))) in g
    assert not any("3gpp.org" in str(o) for o in g.objects())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_output_writer.py tests/test_versioning.py -q`
Expected: FAIL — `ImportError: cannot import name 'module_prefix_map'`.

- [ ] **Step 3: Implement**

In `yang_to_rdf/output_writer.py`:

Replace the imports and delete `INDEX_ONTOLOGY`:

```python
from yang_to_rdf.namespace import (
    aggregate_ontology_iri, module_stem, shapes_module_iri, version_iri,
    vocab_namespace,
)
```

(`module_stem` is now imported rather than defined here; delete the local
definition at lines 56–61. Keep the name exported so `rdf_converter` and `main`
keep importing it from `output_writer` unchanged.)

Add the prefix map and rewrite `module_ns`:

```python
def module_prefix_map(base: str, module_iris: set[str]) -> dict[str, str]:
    """IRI prefix -> owning module IRI.

    Each module contributes two prefixes: its own ontology IRI (classes,
    properties, typedefs) and its shapes ontology IRI. Both route to the same
    module so a module's three output files stay together, while shapes keep a
    namespace of their own -- which is what makes a class named `FooShape`
    unable to collide with the shape of `Foo` (spec §4).
    """
    pmap: dict[str, str] = {}
    for m in module_iris:
        pmap[m] = m
        pmap[shapes_module_iri(base, module_stem(m))] = m
    return pmap


def module_ns(iri, prefix_map: dict[str, str]) -> str | None:
    """Return the module IRI an emitted IRI belongs to, else None.

    A term is `<prefix>#<local>`; the ontology node is `<prefix>` exactly. The
    '#' is required for the term form so `<base>yang/mod` cannot capture
    `<base>yang/mod-extra#X`. Longest match wins as belt-and-braces.
    """
    if not isinstance(iri, URIRef):
        return None
    s = str(iri)
    best_prefix = None
    for prefix in prefix_map:
        if s == prefix or s.startswith(prefix + "#"):
            if best_prefix is None or len(prefix) > len(best_prefix):
                best_prefix = prefix
    return prefix_map[best_prefix] if best_prefix is not None else None
```

`split_graph` keeps its body; change the signature and the two `module_ns`
calls, and key `modules` by the returned module IRI:

```python
def split_graph(g: Graph, prefix_map: dict[str, str]) -> tuple[dict[str, Graph], Graph]:
    """Partition g into {module_iri: Graph} + a leftover index Graph.
    ... (keep the existing docstring body, replacing "module_namespace" with
    "module IRI" and noting that shape IRIs route via prefix_map)
    """
```

Inside, replace `module_ns(s, namespaces)` with `module_ns(s, prefix_map)`. The
final block needs the aggregate IRI, which now comes from the caller — add a
`base_iri` parameter:

```python
def split_graph(g: Graph, prefix_map: dict[str, str],
                base_iri: str) -> tuple[dict[str, Graph], Graph]:
    ...
    index_ontology = URIRef(aggregate_ontology_iri(base_iri))
    index.add((index_ontology, RDF.type, OWL.Ontology))
    for mod in modules:
        modules[mod].add((URIRef(mod), RDF.type, OWL.Ontology))
        index.add((index_ontology, OWL.imports, URIRef(mod)))
    return modules, index
```

In `stamp_versions`, replace the candidate set and the aggregate block:

```python
    candidates = module_prefix_map(model.base_iri,
                                   set(model.revisions) | set(model.module_iris))
    present = set()
    for s in graph.subjects():
        if isinstance(s, URIRef):
            mod = module_ns(s, candidates)
            if mod:
                present.add(mod)
```

and add the provenance emission inside the per-module loop, after
`_stamp_module_meta`:

```python
        _stamp_module_meta(graph, mod, model)
        _stamp_yang_provenance(graph, mod, model)
```

with:

```python
def _stamp_yang_provenance(graph: Graph, mod: str, model) -> None:
    """Record what the module IRI was derived from (spec D6).

    `y2r:yangModuleName` and `y2r:yangNamespace` are minted by this project.
    They exist because module identity is keyed on the declared module name, so
    the YANG `namespace` would otherwise be lost -- and in this module set two
    namespaces disagree with their module name.
    """
    y2r = vocab_namespace(model.base_iri)
    meta = model.module_meta.get(mod)
    if meta is not None:
        graph.add((URIRef(mod), y2r.yangModuleName, Literal(meta.name)))
    urn = model.module_yang_namespace.get(mod)
    if urn:
        graph.add((URIRef(mod), y2r.yangNamespace, URIRef(urn)))
```

Note the loop currently iterates `sorted(model.revisions)`, so a module without
a `revision` statement is never stamped. Change it to iterate
`sorted(model.module_iris)` and make the revision part conditional, so
provenance and metadata land on every module:

```python
    for mod in sorted(model.module_iris):
        if mod not in present:
            continue
        graph.add((URIRef(mod), RDF.type, OWL.Ontology))
        if mod in model.revisions:
            date, cr_ref = model.revisions[mod]
            version_string = f"revision {date}"
            if cr_ref:
                version_string += f" ({cr_ref})"
            graph.add((URIRef(mod), OWL.versionInfo, Literal(version_string)))
        _stamp_module_meta(graph, mod, model)
        _stamp_yang_provenance(graph, mod, model)
```

In the aggregate block, replace `INDEX_ONTOLOGY` with
`URIRef(aggregate_ontology_iri(model.base_iri))` and the version IRI with
`URIRef(version_iri(model.base_iri, release_label))`. In `_aggregate_title`,
`len(model.module_namespaces)` becomes `len(model.module_iris)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_output_writer.py tests/test_versioning.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/output_writer.py tests/test_output_writer.py tests/test_versioning.py
git commit -S -m "Partition on module IRIs; emit YANG provenance

split_graph takes a {prefix -> module} map so shapes, which live in their own
namespace, still travel with their module's files. Term matching requires the
'#' delimiter so one module IRI cannot capture a longer one's terms.
stamp_versions now iterates all modules rather than only those with a revision
statement, so metadata and provenance land on every module.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Converters follow the new scheme

**Files:**
- Modify: `yang_to_rdf/rdf_converter.py`, `yang_to_rdf/shacl_converter.py`, `yang_to_rdf/reference_layer.py`
- Test: `tests/test_rdf_converter.py`, `tests/test_shacl_converter.py`, `tests/test_reference_layer.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `YangToRDFConverter(model)`, `YangToSHACLConverter(model)`, `ReferenceLayerBuilder(model)` — constructors unchanged; each reads `model.base_iri`.

- [ ] **Step 1: Write the failing tests**

Rewrite the three test files to derive every IRI. `tests/test_rdf_converter.py`:

```python
from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from yang_to_rdf.namespace import (
    DEFAULT_BASE_IRI, class_iri, module_iri, namespace_base, property_iri,
    vocab_namespace,
)
from tests._shared import cached_rdf_graph

BASE = DEFAULT_BASE_IRI
Y2R = vocab_namespace(BASE)


def _cls(mod, name):
    return URIRef(class_iri(namespace_base(module_iri(BASE, mod)), name))


def _prop(mod, cls, prop):
    return URIRef(property_iri(namespace_base(module_iri(BASE, mod)), cls, prop))


def test_amffunction_subclasses_managed_function(yang_dir, external_yams_dir):
    g = cached_rdf_graph(yang_dir, external_yams_dir)
    amf = _cls("_3gpp-5gc-nrm-amffunction", "AMFFunction")
    assert (amf, RDF.type, RDFS.Class) in g
    assert (amf, RDFS.subClassOf, Y2R.ManagedFunction) in g


def test_property_iri_is_class_scoped_with_a_dot(yang_dir, external_yams_dir):
    g = cached_rdf_graph(yang_dir, external_yams_dir)
    prop = _prop("_3gpp-5gc-nrm-smffunction", "ThresholdMonitor", "thresholdInfoList")
    assert "#ThresholdMonitor.thresholdInfoList" in str(prop)
    assert (prop, RDF.type, OWL.ObjectProperty) in g


def test_structured_attribute_links_across_modules(yang_dir, external_yams_dir):
    g = cached_rdf_graph(yang_dir, external_yams_dir)
    tm = _cls("_3gpp-5gc-nrm-smffunction", "ThresholdMonitor")
    dt = _cls("_3gpp-common-measurements", "ThresholdInfo")
    assert (tm, Y2R.hasAttribute, dt) in g


def test_dn_reference_has_no_range(yang_dir, external_yams_dir):
    g = cached_rdf_graph(yang_dir, external_yams_dir)
    ref = _prop("_3gpp-5gc-nrm-amffunction", "AMFFunction", "aMFSetRef")
    assert (ref, Y2R.isReference, Literal(True)) in g
    assert (ref, RDFS.range, None) not in g


def test_typedef_is_a_datatype(yang_dir, external_yams_dir):
    g = cached_rdf_graph(yang_dir, external_yams_dir)
    dn = _cls("_3gpp-common-yang-types", "DistinguishedName")
    assert (dn, RDF.type, RDFS.Datatype) in g


def test_property_label_matches_its_local_name(yang_dir, external_yams_dir):
    """The '.' scope separator was already this project's label convention;
    for an unqualified class the IRI local name and the label now coincide."""
    g = cached_rdf_graph(yang_dir, external_yams_dir)
    prop = _prop("_3gpp-5gc-nrm-ausffunction", "AusfInfo", "nFSrvGroupId")
    assert (prop, RDFS.label, Literal("AusfInfo.nFSrvGroupId")) in g


def test_no_3gpp_org_iri_is_emitted(yang_dir, external_yams_dir):
    g = cached_rdf_graph(yang_dir, external_yams_dir)
    bad = [t for t in g for x in t if isinstance(x, URIRef) and "3gpp.org" in str(x)]
    assert not bad, f"{len(bad)} triples still reference 3gpp.org"
```

`tests/test_shacl_converter.py` — same pattern, with the shape derived from the
shapes namespace:

```python
from yang_to_rdf.namespace import (
    DEFAULT_BASE_IRI, class_iri, module_iri, namespace_base, shape_iri,
    shapes_module_iri,
)

BASE = DEFAULT_BASE_IRI


def _shape(mod, name):
    return URIRef(shape_iri(namespace_base(shapes_module_iri(BASE, mod)), name))


def test_shape_targets_its_class(yang_dir, external_yams_dir):
    g = cached_shacl_graph(yang_dir, external_yams_dir)
    shape = _shape("_3gpp-5gc-nrm-amffunction", "AMFFunction")
    cls = URIRef(class_iri(
        namespace_base(module_iri(BASE, "_3gpp-5gc-nrm-amffunction")), "AMFFunction"))
    assert (shape, RDF.type, SH.NodeShape) in g
    assert (shape, SH.targetClass, cls) in g


def test_shape_iri_is_not_a_class_iri(yang_dir, external_yams_dir):
    """Shapes are in <base>shapes/…#, classes in <base>yang/…# (spec §4)."""
    shape = _shape("_3gpp-5gc-nrm-amffunction", "AMFFunction")
    cls = class_iri(namespace_base(module_iri(BASE, "_3gpp-5gc-nrm-amffunction")),
                    "AMFFunctionShape")
    assert str(shape) != cls
```

`tests/test_reference_layer.py` — replace its one hardcoded IRI with `_prop(...)`
built the same way as in `test_rdf_converter.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rdf_converter.py tests/test_shacl_converter.py tests/test_reference_layer.py -q`
Expected: FAIL — the converters still import `NRM` from `namespace`.

- [ ] **Step 3: Implement**

`rdf_converter.py`: replace the import block, take the vocabulary from the model's
base, and fix the stale docstring example.

```python
from yang_to_rdf.namespace import (
    bind_standard_namespaces, class_iri, namespace_base, property_iri,
    vocab_namespace,
)
```

```python
class YangToRDFConverter:
    def __init__(self, model: Model):
        self.model = model
        self.y2r = vocab_namespace(model.base_iri)
        self.graph = Graph()
        bind_standard_namespaces(self.graph, model.base_iri)
        self._labels = self._assign_labels()
```

Replace every `NRM.` with `self.y2r.` (7 occurrences: lines 77–81, 102, 113,
123, 133). In `_assign_labels`, correct the docstring: the qualifying stem is the
full declared module name, so the example is
`_3gpp-5gc-nrm-affunction:File`, not `amffunction:PerfMetricJob`.

`shacl_converter.py`: build shapes in the shapes namespace.

```python
from yang_to_rdf.namespace import (
    bind_standard_namespaces, class_iri, module_stem, namespace_base,
    property_iri, shape_iri, shapes_module_iri,
)
```

```python
    def __init__(self, model: Model):
        self.model = model
        self.graph = Graph()
        bind_standard_namespaces(self.graph, model.base_iri)
        self.graph.bind("sh", SH)

    def _emit_shape(self, cls: Klass):
        g = self.graph
        base = namespace_base(cls.namespace)
        shapes_base = namespace_base(
            shapes_module_iri(self.model.base_iri, module_stem(cls.namespace)))
        cls_uri = URIRef(class_iri(base, cls.name))
        shape = URIRef(shape_iri(shapes_base, cls.name))
        ...
```

`reference_layer.py`: same treatment — import `vocab_namespace`, set
`self.y2r = vocab_namespace(model.base_iri)` in `__init__`, pass
`model.base_iri` to `bind_standard_namespaces`, and replace the five `NRM.` uses
(lines 63, 66, 68, 70).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rdf_converter.py tests/test_shacl_converter.py tests/test_reference_layer.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/rdf_converter.py yang_to_rdf/shacl_converter.py \
        yang_to_rdf/reference_layer.py tests/test_rdf_converter.py \
        tests/test_shacl_converter.py tests/test_reference_layer.py
git commit -S -m "Converters emit y2r: terms and shapes-namespace NodeShapes

Also corrects a stale docstring in rdf_converter._assign_labels: the qualifying
stem is the full declared module name, so the example was wrong.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: The `--base-iri` flag

**Files:**
- Modify: `yang_to_rdf/main.py` (lines 33–52 for args, 68–125 for wiring)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `--base-iri BASE` on the CLI, defaulting to `DEFAULT_BASE_IRI`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_main.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

from yang_to_rdf.namespace import DEFAULT_BASE_IRI


def _run(args, cwd=None):
    return subprocess.run([sys.executable, "-m", "yang_to_rdf.main", *args],
                          capture_output=True, text=True, cwd=cwd)


def test_base_iri_appears_in_help():
    r = _run(["--help"])
    assert r.returncode == 0
    assert "--base-iri" in r.stdout
    assert DEFAULT_BASE_IRI in r.stdout, "the default must be visible to a user"
    assert "not currently dereferenceable" in r.stdout.lower(), \
        "the help text must say the default namespace does not resolve"


def test_invalid_base_iri_is_refused_with_the_reason(tmp_path, tiny_yang_dir):
    r = _run([tiny_yang_dir, "-o", str(tmp_path), "--base-iri", "urn:x:y"])
    assert r.returncode != 0
    assert "RFC 3986" in r.stderr


def test_custom_base_iri_reaches_the_output(tmp_path, tiny_yang_dir):
    r = _run([tiny_yang_dir, "-o", str(tmp_path), "--base-iri", "https://example.org/v1"])
    assert r.returncode == 0, r.stderr
    ttl = (tmp_path / "index.ttl").read_text()
    assert "https://example.org/v1/" in ttl
    assert DEFAULT_BASE_IRI not in ttl


def test_default_output_carries_no_urn_terms(tmp_path, tiny_yang_dir):
    r = _run([tiny_yang_dir, "-o", str(tmp_path)])
    assert r.returncode == 0, r.stderr
    files = sorted(tmp_path.glob("*.ttl"))
    assert files, "no output written"
    text = "\n".join(f.read_text() for f in files)
    # URNs survive only as y2r:yangNamespace provenance objects.
    urn_lines = [ln for ln in text.splitlines()
                 if "<urn:" in ln and "yangNamespace" not in ln]
    assert not urn_lines, f"{len(urn_lines)} non-provenance URN lines remain"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main.py -q`
Expected: FAIL — `--base-iri` is not in `--help`.

- [ ] **Step 3: Implement**

In `yang_to_rdf/main.py`, add the argument after `--output`:

```python
    p.add_argument(
        "--base-iri", dest="base_iri", default=DEFAULT_BASE_IRI,
        help=(f"Base IRI for all emitted terms (default: {DEFAULT_BASE_IRI}). "
              f"Must be an absolute http(s) IRI. The default names an "
              f"Ericsson-owned namespace minted by this project; it is not "
              f"currently dereferenceable and asserts no 3GPP endorsement."))
```

Validate immediately after `parse_args`:

```python
    try:
        args.base_iri = normalize_base_iri(args.base_iri)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

Thread it into the parse and the writer:

```python
    model, errors = parse(yang_files, search_paths, base_iri=args.base_iri)
```

```python
        prefix_map = module_prefix_map(args.base_iri, model.module_iris)
        for layer_name, layer_graph in layers:
            mods, leftover = split_graph(layer_graph, prefix_map, args.base_iri)
```

and update the imports:

```python
from yang_to_rdf.namespace import DEFAULT_BASE_IRI, normalize_base_iri
from yang_to_rdf.output_writer import (
    module_prefix_map, module_stem, split_graph, stamp_versions,
)
```

Bump the `--version` string to `0.3.0`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite and commit**

Run: `uv run pytest -q`
Expected: PASS. `tests/test_build_docs.py` and `tests/test_coverage_audit.py` may
fail on their own hardcoded IRIs — fix those two the same way (derive, don't
retype) before committing, and update `scripts/build_docs.py:10` and
`scripts/coverage_audit.py` for the renamed `Model.module_iris`.

```bash
git add -A
git commit -S -m "Add --base-iri; bump CLI version to 0.3.0

The help text states that the default namespace is ours and does not currently
resolve, so the fact is where a reader is standing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `scripts/iri_census.py` — the gates and the numbers

One committed script is both the gate implementation and the source of every
figure quoted in the spec, so the two cannot drift.

**Files:**
- Create: `scripts/iri_census.py`
- Test: `tests/test_iri_census.py`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces:
  ```python
  @dataclass
  class GateResult:
      gate: str          # "G1" ...
      passed: bool
      checked: int       # size of the candidate set searched
      violations: list[str]
      note: str = ""

  def census(output_dir: Path, base_iri: str) -> list[GateResult]
  def main(argv=None) -> int   # 0 all pass, 1 any fail; prints a table
  ```

- [ ] **Step 1: Write the failing test**

`tests/test_iri_census.py`:

```python
"""Gates G1-G4, G7, G8 over real converted output.

G5, G6 and G9 are NOT here: no real 3GPP YANG can reach them, so they live in
tests/test_namespace.py against constructed input. See spec §8.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.iri_census import census
from yang_to_rdf.namespace import DEFAULT_BASE_IRI


@pytest.fixture(scope="module")
def converted(tmp_path_factory, tiny_yang_dir):
    out = tmp_path_factory.mktemp("census")
    r = subprocess.run([sys.executable, "-m", "yang_to_rdf.main",
                        tiny_yang_dir, "-o", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return out


def test_all_gates_pass_on_real_output(converted):
    results = census(converted, DEFAULT_BASE_IRI)
    failed = [r for r in results if not r.passed]
    assert not failed, "\n".join(f"{r.gate}: {r.violations[:3]}" for r in failed)


def test_every_gate_actually_inspected_something(converted):
    """A gate that searched an empty candidate set has not run (spec §8)."""
    for r in census(converted, DEFAULT_BASE_IRI):
        assert r.checked > 0, f"{r.gate} inspected 0 candidates"


def test_expected_gates_are_all_present(converted):
    """Assert the gate count, so adding a gate without wiring it fails loudly."""
    gates = {r.gate for r in census(converted, DEFAULT_BASE_IRI)}
    assert gates == {"G1", "G2", "G3", "G4", "G7", "G8"}


def test_cli_exits_zero_and_prints_counts(converted):
    r = subprocess.run([sys.executable, "-m", "scripts.iri_census",
                        str(converted), "--base-iri", DEFAULT_BASE_IRI],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "G1" in r.stdout and "checked" in r.stdout
    assert r.stdout.strip(), "a check that printed nothing has not run"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_iri_census.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.iri_census'`.
If `scripts/` is not importable, add `scripts/__init__.py` in this task.

- [ ] **Step 3: Implement `scripts/iri_census.py`**

```python
#!/usr/bin/env python3
"""Census + gates over emitted IRIs.

Answers: are all emitted IRIs valid absolute http(s) URLs, are they injective,
did any URN survive, do they survive an rdflib round-trip, and is every local
name a legal NCName? Gate definitions and expectations:
docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md §8.

This is the single definition of these numbers. Documentation that quotes them
names this script; do not re-derive them with an ad-hoc walk.

Usage:
    uv run python -m scripts.iri_census OUTPUT_DIR [--base-iri BASE] [--json PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from rdflib import Graph, URIRef

from yang_to_rdf.namespace import DEFAULT_BASE_IRI, NCNAME_RE, normalize_base_iri

# Emitted vocabularies we do not own and must not police as ours.
FOREIGN_PREFIXES = (
    "http://www.w3.org/", "http://purl.org/dc/", "https://www.w3.org/",
)


@dataclass
class GateResult:
    gate: str
    passed: bool
    checked: int
    violations: list[str] = field(default_factory=list)
    note: str = ""


def _load(output_dir: Path) -> dict[Path, Graph]:
    graphs = {}
    for p in sorted(output_dir.glob("*.ttl")):
        g = Graph()
        g.parse(p, format="turtle")
        graphs[p] = g
    if not graphs:
        raise SystemExit(f"no .ttl files in {output_dir} -- nothing to check")
    return graphs


def _all_uris(graphs) -> set[str]:
    out = set()
    for g in graphs.values():
        for triple in g:
            for term in triple:
                if isinstance(term, URIRef):
                    out.add(str(term))
    return out


def _ours(uris, base: str) -> set[str]:
    return {u for u in uris if u.startswith(base)}


def g1_absolute_http(uris) -> GateResult:
    bad = []
    for u in uris:
        parts = urlsplit(u)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            bad.append(u)
    return GateResult("G1", not bad, len(uris), sorted(bad)[:20],
                      "every emitted IRI is an absolute http(s) URL")


def g2_injective(graphs, base: str) -> GateResult:
    """(module, class[, prop]) -> IRI must be injective.

    Checked structurally: decompose each of our IRIs into (namespace, local)
    and confirm no two distinct decompositions produce one IRI. Since the IRI
    IS the join, a collision shows up as one local name reachable from two
    different (class, prop) splits -- which is what the '.' separator risks.
    """
    ours = _ours(_all_uris(graphs), base)
    terms = [u for u in ours if "#" in u]
    splits = defaultdict(set)
    for u in terms:
        ns, local = u.rsplit("#", 1)
        # every way this local name could have been produced
        for i, ch in enumerate(local):
            if ch == ".":
                splits[u].add((ns, local[:i], local[i + 1:]))
        if "." not in local:
            splits[u].add((ns, local, None))
    ambiguous = [u for u, s in splits.items() if len(s) > 1]
    counts = Counter(terms)
    dupes = [u for u, n in counts.items() if n > 1]
    bad = sorted(ambiguous + dupes)[:20]
    return GateResult("G2", not bad, len(terms), bad,
                      f"{len(terms)} terms, {len(set(terms))} distinct")


def g3_no_urn_leak(graphs) -> GateResult:
    """No URN survives except as a y2r:yangNamespace provenance object."""
    from yang_to_rdf.namespace import vocab_namespace
    leaked, provenance = [], 0
    for g in graphs.values():
        prov_pred = None
        for p in set(g.predicates()):
            if str(p).endswith("#yangNamespace"):
                prov_pred = p
        for s, p, o in g:
            for term in (s, p, o):
                if isinstance(term, URIRef) and str(term).startswith("urn:"):
                    if term is o and p == prov_pred:
                        provenance += 1
                    else:
                        leaked.append(f"{term} via {p}")
    return GateResult("G3", not leaked, provenance + len(leaked), sorted(leaked)[:20],
                      f"{provenance} provenance URNs kept, {len(leaked)} leaked")


def g4_round_trip(graphs) -> GateResult:
    bad = []
    for path, g in graphs.items():
        h = Graph()
        h.parse(data=g.serialize(format="turtle"), format="turtle")
        if set(g) != set(h):
            bad.append(f"{path.name}: {len(g)} -> {len(h)}")
    return GateResult("G4", not bad, len(graphs), bad,
                      "serialize -> parse -> compare, per file")


def g7_filename_matches_module(graphs, base: str) -> GateResult:
    """Each <stem>_<layer>.ttl must correspond to a module IRI of that stem."""
    bad = []
    checked = 0
    for path, g in graphs.items():
        if path.name == "index.ttl":
            continue
        stem = re.sub(r"_(rdf|shacl|refs)$", "", path.stem)
        checked += 1
        expected = f"{base}yang/{stem}"
        subjects = {str(s) for s in g.subjects() if isinstance(s, URIRef)}
        if not any(s == expected or s.startswith(expected + "#")
                   or s.startswith(f"{base}shapes/{stem}#") for s in subjects):
            bad.append(f"{path.name}: no term under {expected}")
    return GateResult("G7", not bad, checked, bad,
                      "output filename stem matches its module IRI")


def g8_ncname_locals(graphs, base: str) -> GateResult:
    ours = _ours(_all_uris(graphs), base)
    terms = [u for u in ours if "#" in u]
    bad = [u for u in terms if not NCNAME_RE.match(u.rsplit("#", 1)[1])]
    return GateResult("G8", not bad, len(terms), sorted(bad)[:20],
                      "every local name is a legal NCName (XML Names Rec)")


def census(output_dir: Path, base_iri: str) -> list[GateResult]:
    base = normalize_base_iri(base_iri)
    graphs = _load(Path(output_dir))
    uris = _all_uris(graphs)
    return [
        g1_absolute_http(uris),
        g2_injective(graphs, base),
        g3_no_urn_leak(graphs),
        g4_round_trip(graphs),
        g7_filename_matches_module(graphs, base),
        g8_ncname_locals(graphs, base),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--base-iri", default=DEFAULT_BASE_IRI)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)

    results = census(a.output_dir, a.base_iri)
    print(f"{'gate':6s} {'result':8s} {'checked':>9s}  note")
    for r in results:
        print(f"{r.gate:6s} {'PASS' if r.passed else 'FAIL':8s} "
              f"{r.checked:9d}  {r.note}")
        for v in r.violations:
            print(f"         - {v}")
    if a.json:
        a.json.write_text(json.dumps([asdict(r) for r in results], indent=2))
    failed = [r for r in results if not r.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} gates passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_iri_census.py -q`
Expected: PASS.

- [ ] **Step 5: Run it against the full set and record the table**

```bash
uv run yang-to-rdf MnS-Rel-19-yang-models.zip -o /tmp/full-out
uv run python -m scripts.iri_census /tmp/full-out
```

Expected: all 6 gates PASS. **Paste the printed table into the task report.** G3
should report **118** provenance URNs kept and 0 leaked; if the number differs,
stop and explain it rather than adjusting the expectation.

- [ ] **Step 6: Commit**

```bash
git add scripts/iri_census.py scripts/__init__.py tests/test_iri_census.py
git commit -S -m "Add scripts/iri_census.py: gates G1-G4, G7, G8

Single definition of the IRI figures quoted in the design doc, so gate and
measurement cannot drift. Every gate reports the size of the candidate set it
searched, and the test suite asserts both the gate count and that no gate
inspected zero candidates.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Break every gate and watch it fail

A gate nobody has watched fail is a decoration. This task produces **evidence**,
not code.

**Files:**
- Modify: none permanently. Every change here is reverted.
- Create: `docs/superpowers/plans/2026-09-17-gate-inversion-log.md`

- [ ] **Step 1: Invert G1**

In `namespace.py`, temporarily change `DEFAULT_BASE_IRI` to `"urn:x:y:"` and
bypass `normalize_base_iri`. Run `uv run python -m scripts.iri_census /tmp/full-out`.
Expected: **G1 FAIL**. Record the message. Revert.

- [ ] **Step 2: Invert G2**

Temporarily change `SCOPE_SEPARATOR` to `""` so `Foo` + `bar` becomes `Foobar`,
regenerate a tiny output, run the census.
Expected: **G2 FAIL** with ambiguous decompositions. Revert.

- [ ] **Step 3: Invert G3**

Temporarily make `module_iri()` return the YANG namespace URN. Regenerate, run
the census. Expected: **G3 FAIL** with a large leak count. Revert.

- [ ] **Step 4: Invert G6 and G9 (the fixture gates)**

Delete the `SCOPE_SEPARATOR in name` check from `_check_identifier` and run
`uv run pytest tests/test_namespace.py -q`.
Expected: the two separator tests **FAIL**. Restore.

Then make `shape_iri` build in the class namespace instead of the shapes
namespace and run `uv run pytest tests/test_namespace.py::test_shapes_live_in_a_separate_namespace tests/test_output_writer.py -q`.
Expected: **FAIL**. Restore.

- [ ] **Step 5: Invert G8**

Temporarily loosen `NCNAME_RE` to `re.compile(r".*", re.S)` and run
`uv run pytest tests/test_namespace.py -q`.
Expected: the NCName rejection tests **FAIL**. Revert.

- [ ] **Step 6: If any inversion did NOT fail, stop**

An inversion that cannot fail is a finding about the sample, not a pass. Work out
which input would exhibit the defect, add it to the test, and re-run. Do not
record the gate as trusted until you have seen it red.

- [ ] **Step 7: Write the log and commit**

Record, per gate: the exact edit, the observed failure output, and whether a
second defence masked it. Then:

```bash
git add docs/superpowers/plans/2026-09-17-gate-inversion-log.md
git commit -S -m "Record observed failures for every IRI gate

Each gate was inverted and watched to fail before being trusted. Log gives the
edit and the failure output per gate.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Container + install-doc anti-drift

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `scripts/verify.py`
- Modify: `README.md` (Install section only)
- Test: `tests/test_verify.py`, `tests/test_install_docs.py`

**Interfaces:**
- Consumes: Task 6's `census`.
- Produces:
  ```python
  # scripts/verify.py
  def readme_install_commands(readme: Path) -> list[str]
  def main(argv=None) -> int   # 0 all stages pass
  STAGE_COUNT: int = 8
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_install_docs.py`:

```python
"""The Dockerfile IS the install documentation; they must not drift."""
from pathlib import Path

from scripts.verify import readme_install_commands

ROOT = Path(__file__).resolve().parent.parent


def test_readme_install_commands_are_found():
    cmds = readme_install_commands(ROOT / "README.md")
    assert cmds, "extracted 0 commands -- a renamed heading would silently pass"
    assert len(cmds) >= 2


def test_every_readme_install_command_appears_in_the_dockerfile():
    cmds = readme_install_commands(ROOT / "README.md")
    dockerfile = (ROOT / "Dockerfile").read_text()
    missing = [c for c in cmds if c not in dockerfile]
    assert not missing, (
        f"{len(missing)} of {len(cmds)} README install commands are not in the "
        f"Dockerfile: {missing}")


def test_the_documented_substitution_is_declared():
    """git clone is the one command the container replaces; say so in place."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "git clone" in dockerfile, \
        "the Dockerfile must name the command it substitutes, in a comment"
```

`tests/test_verify.py`:

```python
import subprocess
import sys

from scripts.verify import STAGE_COUNT


def test_stage_count_is_asserted():
    """Adding a stage without summarising it must fail (spec §9)."""
    from scripts import verify
    names = verify.stage_names()
    assert len(names) == STAGE_COUNT, \
        f"{len(names)} stages defined but STAGE_COUNT is {STAGE_COUNT}"


def test_offline_mode_refuses_to_claim_success_for_skipped_stages():
    r = subprocess.run([sys.executable, "-m", "scripts.verify", "--offline",
                        "--dry-run"], capture_output=True, text=True)
    assert "SKIP" in r.stdout
    assert "network" in r.stdout.lower(), "a skip must state its reason"
    assert "all stages passed" not in r.stdout.lower()


def test_network_stages_fail_rather_than_skip_by_default():
    r = subprocess.run([sys.executable, "-m", "scripts.verify", "--dry-run",
                        "--simulate-no-network"], capture_output=True, text=True)
    assert r.returncode != 0, "missing network must fail, not skip"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_install_docs.py tests/test_verify.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.verify'`.

- [ ] **Step 3: Write the README Install section, the Dockerfile, and verify.py**

`README.md` Install section — fenced `bash` block, one command per line, so the
extractor has a stable contract:

````markdown
## Install

Requires Python ≥ 3.10 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/EricssonResearch/yang-to-rdf.git
cd yang-to-rdf
uv sync --locked
```

The [`Dockerfile`](Dockerfile) runs exactly these commands from a clean
`python:3.12-slim` base and is verified in CI, so these instructions cannot go
stale. The container substitutes `COPY` for the `git clone` line — that is the
only difference.
````

`Dockerfile`:

```dockerfile
# The install documentation, executable.
#
# Every RUN below is a verbatim command from README.md's Install section; a test
# (tests/test_install_docs.py) asserts that correspondence so the two cannot
# drift. The ONE substitution: the README says
#   git clone https://github.com/EricssonResearch/yang-to-rdf.git
# and we COPY instead, so the image builds before publication and in CI.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /yang-to-rdf
COPY . .

RUN uv sync --locked

ENTRYPOINT ["uv", "run", "python", "-m", "scripts.verify"]
CMD []
```

`.dockerignore`:

```
.git
.venv
output
dist
examples
*.zip
__pycache__
.pytest_cache
```

Note `examples/` is excluded from the build context but stage 6 needs it — mount
it at run time (`-v "$PWD/examples:/yang-to-rdf/examples:ro"`) or drop it from
`.dockerignore` if the image size is acceptable. Pick one and document it in the
README next to the `docker run` line.

`scripts/verify.py` — one entry point, eight stages, each stating its
prerequisite:

```python
#!/usr/bin/env python3
"""Verify this repository from a clean base: install, test, package, convert,
gate, and reproduce the committed examples.

Stages and their expectations:
docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md §9.

Every run writes verification-report.json, stamped with the git HEAD and whether
the tree was dirty -- numbers from a dirty tree are not reproducible and are
marked as such.

Usage:
    uv run python -m scripts.verify [--offline] [--output DIR]
"""
```

Implement with a `STAGES` list of `(name, callable)` pairs, `stage_names()`
returning the names, and `STAGE_COUNT = len(STAGES)` asserted by the test. The
pinned fetch is `--fetch-release Tag_Rel19_SA112 --ref-type tags`. Stage 6 diffs
the produced directory against `examples/MnS-Rel-19-yang-models/` and reports the
count of differing files with an expectation of **zero**. Without network,
stages 4–6 raise; only `--offline` converts them to `SKIP`, and in that mode the
final line must not claim overall success.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_install_docs.py tests/test_verify.py -q`
Expected: PASS.

- [ ] **Step 5: Build and run the container for real**

```bash
docker build -t yang-to-rdf .
docker run --rm -v "$PWD/examples:/yang-to-rdf/examples:ro" yang-to-rdf
```

Expected: 8/8 stages pass. **Paste the stage table into the task report.** Stage 6
will fail until Task 9 regenerates the examples — that is expected here; record
the differing-file count, do not weaken the gate.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore scripts/verify.py tests/test_verify.py \
        tests/test_install_docs.py README.md
git commit -S -m "Add container verification; make the Dockerfile the install docs

The Dockerfile runs the README's install commands verbatim from a clean base,
with a test asserting the correspondence and asserting the extracted command
count is non-zero. Missing network fails stages 4-6 rather than skipping them.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Regenerate `examples/` from the pinned tag

**Files:**
- Modify: all 287 files under `examples/MnS-Rel-19-yang-models/`
- Create/modify: `examples/MnS-Rel-19-yang-models/README.md`

- [ ] **Step 1: Record the current state, then regenerate**

```bash
git rev-parse HEAD > /tmp/before-head
uv run yang-to-rdf --fetch-release Tag_Rel19_SA112 --ref-type tags \
    -o examples/MnS-Rel-19-yang-models/
```

- [ ] **Step 2: Report the diff BEFORE committing**

```bash
git diff --stat examples/ | tail -3
git status --short examples/ | awk '{print $1}' | sort | uniq -c
```

Report: how many files changed, added, deleted; and the two filename corrections
(`extternalseppfunction` → `externalseppfunction`,
`nrnetwork-nrsectorcarrier` → `nrsectorcarrier`). **Do not guess the extent of
upstream movement between the old July branch snapshot and this tag — state the
measured numbers.** If the class or module count moved, say by how much and why.

- [ ] **Step 3: Re-run the gates on the committed examples**

```bash
uv run python -m scripts.iri_census examples/MnS-Rel-19-yang-models
```
Expected: 6/6 PASS, G3 reporting 118 provenance URNs.

- [ ] **Step 4: Confirm determinism**

```bash
uv run yang-to-rdf --fetch-release Tag_Rel19_SA112 --ref-type tags -o /tmp/again
diff -rq /tmp/again examples/MnS-Rel-19-yang-models/ && echo "byte-identical"
```
Expected: `byte-identical`. This is what stage 6 of the container asserts.

- [ ] **Step 5: Write the provenance README and commit**

`examples/MnS-Rel-19-yang-models/README.md` must state: the forge URL, the tag
`Tag_Rel19_SA112`, the commit `24ffa42e`, the tool version, the exact command,
and that re-running it reproduces these files byte-for-byte.

```bash
git add examples/
git commit -S -m "Regenerate examples from forge tag Tag_Rel19_SA112 (24ffa42e)

Pinned to an immutable tag so a third party can byte-reproduce examples/; the
previous snapshot came from a moving branch and could not be re-derived. Two
filenames are corrected by keying on the module name.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Documentation, scrub, CI, version

**Files:**
- Modify: `CONVERSION_NOTES.md`, `VERSIONING.md`, `README.md`, `CHANGELOG.md`, `pyproject.toml`, `.github/workflows/ci.yml`
- Delete: `.gitlab-ci.yml`
- Test: `tests/test_no_internal_references.py` (create)

- [ ] **Step 1: Write the failing scrub test**

```python
"""No internal Ericsson references may ship in a public repository."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# (the concrete internal hostnames live in the test itself, not in this plan)
FORBIDDEN = (INTERNAL_HOSTNAMES + ("3gpp.org/nrm/", "--base-namespace"))


def test_no_forbidden_strings_in_tracked_files():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True, check=True
                             ).stdout.split()
    assert tracked, "git ls-files returned nothing -- the check did not run"
    hits = []
    for rel in tracked:
        p = ROOT / rel
        if not p.is_file() or p.suffix in (".ttl", ".zip"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for bad in FORBIDDEN:
            if bad in text:
                hits.append(f"{rel}: {bad}")
    assert not hits, f"{len(hits)} internal/stale references in {len(tracked)} tracked files:\n" + "\n".join(hits)


def test_gitlab_ci_is_gone():
    assert not (ROOT / ".gitlab-ci.yml").exists()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_no_internal_references.py -q`
Expected: FAIL, listing the README Pages link, the five `--base-namespace`
references, and the `3gpp.org/nrm/` mentions.

- [ ] **Step 3: Make the edits**

- `README.md`: delete the internal Pages link entirely (no replacement — see spec
  §11). Rewrite the **IRI Strategy** section for the new scheme with a worked
  example. Rename `nrm:` → `y2r:` in the NRM Vocabulary section and say the
  namespace is ours and does not currently resolve. Add the `docker run` line.
- `CONVERSION_NOTES.md`: §1 base becomes `<base>vocab#`, prefix `y2r:`; add the
  three reference-layer predicates plus `yangModuleName`/`yangNamespace` to the
  table; add a subsection recording the `.` separator as ours (noting it was
  already the `rdfs:label` convention) and the non-dereferenceable default with
  its reference-status table from the spec. §2's `module` row: IRI is now
  `<base>yang/<declared module name>`, with the two corrected modules named.
- `VERSIONING.md`: replace every URN example with the new IRIs; replace all four
  `--base-namespace` uses with `--base-iri`; re-ground the "IRIs are
  release-agnostic" claim on **module-name** stability, and cite RFC 7950 only
  for what it actually says.
- `CHANGELOG.md`: a `[0.3.0]` section — Changed: the IRI scheme (old → new rule),
  `nrm:` → `y2r:`; Added: `--base-iri`, `scripts/iri_census.py`,
  `scripts/verify.py`, `Dockerfile`, pinned examples; Fixed: two module
  identities, `--base-namespace` documented but absent, the stale
  `_assign_labels` docstring.
- `pyproject.toml`: `version = "0.3.0"`.
- Delete `.gitlab-ci.yml`.
- `.github/workflows/ci.yml`: add a `verify` job that runs
  `docker build -t yang-to-rdf .` then the container. Mark it
  `continue-on-error: false` but note in a comment that it needs egress to
  `forge.3gpp.org`; **whether GitHub runners can reach the 3GPP forge is not
  verified from here** — state that in the comment rather than assuming it.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, all files.

- [ ] **Step 5: Run ruff, read its real exit status, fix, and only then commit**

```bash
uv run ruff check .
echo "ruff exit=$?"
```

Fix anything reported. Re-run until clean. **Commit as a separate command**, not
chained after the check.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -S -m "Docs, scrub, CI, 0.3.0

Removes internal Ericsson references, deletes .gitlab-ci.yml, and adds a CI job
that builds and runs the verification container. Corrects --base-namespace,
documented in five places but never implemented, to --base-iri.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** D1→Tasks 1,5. D2→Task 2. D3,D4→Task 1. D5→Tasks 1,3,4.
D6→Tasks 2,3. D7→Tasks 1,4. §5 config + the `--base-namespace` defect→Tasks 5,10.
§6 file table→Tasks 1–5,10. §7 non-dereferenceable disclosure→Tasks 1,5,10.
§8 gates G1–G9→Tasks 1 (G5,G6,G9), 6 (G1–G4,G7,G8), 7 (inversion).
§9 container→Task 8. §10 pinned examples→Task 9. §11 out-of-scope: nothing
implements Pages or pyLODE, as intended. §12 figures→Task 6 owns them.

**Gaps found and closed while reviewing:** the spec's §6 table lists
`reference_layer.py` but gave it no gate coverage — folded into Task 4. `scripts/`
needed `__init__.py` to be importable by the census tests — added to Task 6.
`split_graph` needed a `base_iri` parameter once `INDEX_ONTOLOGY` stopped being a
constant — added to Task 3's interface.

**Known rough edge, deliberately left for the implementer:** Task 8's
`.dockerignore` excludes `examples/` while stage 6 needs it. Both resolutions are
sound; the task says to pick one and document it rather than pretending there is
no tension.

**Type consistency.** `module_iri`, `namespace_base`, `class_iri`,
`property_iri`, `shape_iri`, `shapes_module_iri`, `module_stem`,
`normalize_base_iri`, `vocab_namespace`, `aggregate_ontology_iri`, `version_iri`
are spelled identically in Tasks 1–6. `Model.module_iris` (renamed from
`module_namespaces`) is used consistently in Tasks 2, 3, 5 and its call sites in
`main.py`, `output_writer.py` and `scripts/coverage_audit.py` are all named.
`GateResult.checked` is read by Task 6's tests under that name.
