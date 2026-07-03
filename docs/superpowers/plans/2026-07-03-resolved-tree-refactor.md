# Resolved-Tree Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild yang-to-rdf's parser on pyang's *resolved* schema tree (replacing string heuristics), converting unambiguous facts into base RDF/SHACL and inferred reference-ranges into a separate auditable extension layer.

**Architecture:** `input_handler` collects a complete 3GPP module set plus its bundled `external-yams/` search path → `yang_parser` builds a dataclass IR from pyang's resolved tree (`i_children`, `i_typedefs`, `augment.i_target_node`, resolved type chains) → `rdf_converter` and `shacl_converter` emit base graphs → `reference_layer` emits the inferred-range extension graph. Executed strictly test-first so each resolved-tree assumption is proven before the next unit builds on it.

**Tech Stack:** Python ≥3.10, pyang ≥2.6, rdflib ≥7, pytest, uv.

## Global Constraints

- Python ≥3.10; dependencies limited to `pyang>=2.6.0`, `rdflib>=7.0.0` (plus `pytest` as a dev dep). No new runtime dependency (no libyang).
- The tool targets a **complete** module set. Reference set: `MnS-Rel-19-yang-models.zip` at repo root (git-ignored via `*.zip`). Tests run against it.
- pyang search path MUST use the set's own `external-yams/` folder and MUST NOT include pyang's bundled IETF modules.
- IRI scheme (unchanged): class = `<module-namespace>/ClassName`; property = `<module-namespace>/ClassName/propertyName`; module base = `<yang-namespace>/`.
- `nrm:` vocab base = `https://3gpp.org/nrm/vocab#`. New terms: `nrm:isReference`, `nrm:isInvariant`, `nrm:inferredBy`, `nrm:confidence`.
- Commits: authored as the configured local identity (Jean Martins <jean.martins@ericsson.com>), GPG-signed (`git commit -S`). No co-author trailers. Do NOT push.
- Extension keyword for invariants (from pyang) is the tuple `('_3gpp-common-yang-extensions', 'inVariant')` on a leaf's `substmts`, readable directly on resolved `i_children` nodes (verified: 67 authored → 1378 leaf instances).
- DN detection is by resolved type chain bottoming out at `DistinguishedName`/`Dn`/`LDN` — never by leaf-name.
- 3GPP `<<dataType>>` structured attributes (nested `list` inside an IOC's `attributes` container) are modeled as their own `rdfs:Class` linked by an `owl:ObjectProperty` (+ `nrm:hasAttribute`), NOT flattened and NOT dropped — applies to both singleton (min=1/max=1) and multivalued nested lists. An IOC is any `list` whose `i_children` has an `attributes` container.

## Reference Facts (verified against the set; use in assertions)

- `ManagedElement` module namespace: `urn:3gpp:sa5:_3gpp-common-managed-element` → class IRI `urn:3gpp:sa5:_3gpp-common-managed-element/ManagedElement`.
- `AMFFunction` module namespace: `urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction` → class IRI `urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction`.
- `AMFFunctionGrp` `uses mf3gpp:ManagedFunctionGrp` (→ `rdfs:subClassOf nrm:ManagedFunction`).
- Concrete invariant leaf: `nFSrvGroupId` in `_3gpp-5gc-nrm-ausffunction`.
- Enum typedef: `CommModelType` in `_3gpp-5g-common-yang-types`. Pattern typedef: `UTC24TimeOfDayT` (same module). DN typedef: `DistinguishedName` in `_3gpp-common-yang-types`.
- Unambiguous DN ref example: `aMFSetRef` (→ `AMFSet`). Unresolved DN ref example: `_5GCNFRef`.
- Complete set validates to **0 errors, 118 modules**.

## File Structure

- `yang_to_rdf/pyang_context.py` — **new**. Builds a properly-bootstrapped pyang `Context` (real optparse opts via `plugin.init`), validates, surfaces errors. One responsibility: "give me a validated pyang context from files + search paths."
- `yang_to_rdf/input_handler.py` — modify. Add `external-yams` detection, zip-slip guard, tempdir cleanup.
- `yang_to_rdf/yang_parser.py` — **rewrite**. IR dataclasses (`Leaf`, `AttrRef`, `Klass` with `kind` ioc/datatype, `Typedef`, `Model`) + resolved-tree walk producing IOC classes, dataType classes, containment, and inheritance.
- `yang_to_rdf/type_resolver.py` — **new**. Shared YANG-type→(XSD datatype | typedef datatype IRI | DN-marker) resolution, following the typedef chain. Consumed by both converters and the parser.
- `yang_to_rdf/rdf_converter.py` — modify. Consume IR; IOC + dataType classes; `nrm:hasAttribute` links; DN→object property; invariant annotation; typedef→`rdfs:Datatype`.
- `yang_to_rdf/shacl_converter.py` — modify. Consume IR; one NodeShape per class (IOC + dataType); inherited leaves already materialized in IR; dataType attrs via `sh:class`.
- `yang_to_rdf/reference_layer.py` — **new**. Build extension graph from IR: unambiguous ranges + unresolved worklist, with provenance.
- `yang_to_rdf/main.py` — modify. `--no-inference`; emit `<stem>_refs.ttl`; updated examples.
- `tests/conftest.py` — **new**. Session fixture: locate the zip, parse once, expose IR + graphs.
- `tests/test_*.py` — **new**. Per-unit tests.
- `README.md` — modify. Full-set usage, extension layer, no k20 examples.

Test data resolution: `conftest.py` locates `MnS-Rel-19-yang-models.zip` via env var `YANG_TEST_ZIP` if set, else `<repo-root>/MnS-Rel-19-yang-models.zip`; if absent, tests `pytest.skip` with a clear message.

---

### Task 1: pyang context bootstrap + error surfacing

**Files:**
- Create: `yang_to_rdf/pyang_context.py`
- Test: `tests/test_pyang_context.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: `build_context(yang_files: list[str], search_paths: list[str]) -> tuple[pyang.context.Context, list[str]]` — returns the validated context and a list of human-readable error strings for tags worse than `UNUSED_IMPORT` (empty list = clean). Also `SUPPRESSED_ERROR_TAGS: set[str] = {"UNUSED_IMPORT"}`.
- Produces (conftest): fixture `yang_dir` → path to extracted `yang-models/` dir; `external_yams_dir` → its `external-yams/` subdir; `parsed_context` → `build_context(...)` result over the full set.

- [ ] **Step 1: Write conftest fixtures**

```python
# tests/conftest.py
import os, glob, zipfile, tempfile, shutil
from pathlib import Path
import pytest

def _find_zip():
    env = os.environ.get("YANG_TEST_ZIP")
    if env and Path(env).is_file():
        return Path(env)
    cand = Path(__file__).resolve().parent.parent / "MnS-Rel-19-yang-models.zip"
    return cand if cand.is_file() else None

@pytest.fixture(scope="session")
def extracted_set():
    zp = _find_zip()
    if zp is None:
        pytest.skip("MnS-Rel-19-yang-models.zip not found (set YANG_TEST_ZIP)")
    d = tempfile.mkdtemp(prefix="yang_test_")
    with zipfile.ZipFile(zp) as zf:
        zf.extractall(d)
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture(scope="session")
def yang_dir(extracted_set):
    hits = glob.glob(os.path.join(extracted_set, "**", "_3gpp-common-managed-element.yang"), recursive=True)
    assert hits, "yang-models dir not found in zip"
    return str(Path(hits[0]).parent)

@pytest.fixture(scope="session")
def external_yams_dir(yang_dir):
    return str(Path(yang_dir) / "external-yams")
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_pyang_context.py
import glob, os
from yang_to_rdf.pyang_context import build_context

def test_full_set_validates_cleanly(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    ctx, errors = build_context(files, [yang_dir, external_yams_dir])
    assert errors == [], f"expected clean validation, got: {errors[:5]}"
    modules = [m for m in ctx.modules.values() if m.keyword == "module"]
    assert len(modules) == 118

def test_incomplete_set_surfaces_errors(yang_dir):
    # No external-yams on the path -> unresolved imports must be reported, not swallowed.
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    ctx, errors = build_context(files, [yang_dir])
    assert any("MODULE_NOT_FOUND" in e for e in errors)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_pyang_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'yang_to_rdf.pyang_context'`.

- [ ] **Step 4: Write minimal implementation**

```python
# yang_to_rdf/pyang_context.py
"""Bootstrap a validated pyang Context using pyang's real option handling."""
from __future__ import annotations

import optparse

from pyang import plugin
from pyang.context import Context
from pyang.repository import FileRepository

SUPPRESSED_ERROR_TAGS = {"UNUSED_IMPORT"}


def _build_optparser() -> optparse.OptionParser:
    op = optparse.OptionParser("", add_help_option=False)
    op.add_option("-p", "--path", dest="path", default=[], action="append")
    plugin.init([])
    for p in plugin.plugins:
        p.add_opts(op)
    return op


def build_context(
    yang_files: list[str], search_paths: list[str]
) -> tuple[Context, list[str]]:
    """Parse and validate yang_files. Returns (context, error_messages).

    error_messages excludes benign tags (SUPPRESSED_ERROR_TAGS); an empty list
    means validation is clean enough to convert.
    """
    primary = search_paths[0] if search_paths else "."
    repo = FileRepository(primary, use_env=False)
    repo.dirs = list(search_paths)

    ctx = Context(repo)
    (opts, _) = _build_optparser().parse_args([])
    opts.path = list(search_paths)
    ctx.opts = opts

    for fpath in yang_files:
        with open(fpath, "r", encoding="utf-8") as f:
            ctx.add_module(fpath, f.read())
    ctx.validate()

    errors: list[str] = []
    for epos, tag, args in ctx.errors:
        if tag in SUPPRESSED_ERROR_TAGS:
            continue
        errors.append(f"{epos}: {tag} {args}")
    return ctx, errors
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pyang_context.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add yang_to_rdf/pyang_context.py tests/conftest.py tests/test_pyang_context.py
git commit -S -m "Add pyang context bootstrap with error surfacing"
```

---

### Task 2: input_handler — external-yams, zip-slip guard, cleanup

**Files:**
- Modify: `yang_to_rdf/input_handler.py`
- Test: `tests/test_input_handler.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `collect_yang_files(input_paths: list[str]) -> tuple[list[str], list[str]]` (unchanged signature). Behavior change: when a directory or extracted zip contains an `external-yams/` (or `external-yangs/`) subfolder, that subfolder is appended to `search_paths`. `.yang` files under any `external-yams/` folder are excluded from the returned *conversion* file list (they are dependencies, not conversion targets). `_extract_zip(zip_path) -> tuple[list[str], str]` rejects members whose normalized path escapes the extraction dir (raises `ValueError`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_input_handler.py
import os, zipfile
import pytest
from yang_to_rdf.input_handler import collect_yang_files, _extract_zip

def test_external_yams_added_to_search_path(tmp_path):
    root = tmp_path / "set"
    (root / "external-yams").mkdir(parents=True)
    (root / "a.yang").write_text("module a {}")
    (root / "external-yams" / "dep.yang").write_text("module dep {}")
    files, paths = collect_yang_files([str(root)])
    assert any(p.endswith("external-yams") for p in paths)
    # dependency module is NOT a conversion target
    assert not any(f.endswith("dep.yang") for f in files)
    assert any(f.endswith("a.yang") for f in files)

def test_zip_slip_rejected(tmp_path):
    bad = tmp_path / "evil.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../escape.yang", "module x {}")
    with pytest.raises(ValueError):
        _extract_zip(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_input_handler.py -v`
Expected: FAIL (external-yams not on path / no zip-slip guard).

- [ ] **Step 3: Write implementation**

Replace the body of `yang_to_rdf/input_handler.py` with:

```python
"""Handle input sources: zip files, directories, individual .yang files."""
from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

EXTERNAL_DIR_NAMES = {"external-yams", "external-yangs"}


def _is_external(path: Path) -> bool:
    return any(part in EXTERNAL_DIR_NAMES for part in path.parts)


def _augment_search_paths(root: Path, search_paths: list[str]) -> None:
    for name in EXTERNAL_DIR_NAMES:
        ext = root / name
        if ext.is_dir():
            search_paths.append(str(ext))


def collect_yang_files(input_paths: list[str]) -> tuple[list[str], list[str]]:
    """Collect .yang conversion targets and pyang search paths from inputs."""
    all_files: list[str] = []
    search_paths: list[str] = []

    for input_path in input_paths:
        path = Path(input_path)
        if path.is_file() and path.suffix == ".zip":
            files, sp = _extract_zip(path)
            all_files.extend(files)
            search_paths.append(sp)
            _augment_search_paths(Path(sp), search_paths)
            # nested yang-models dir inside zip
            for child in Path(sp).rglob("external-yams"):
                if child.is_dir():
                    search_paths.append(str(child))
                    search_paths.append(str(child.parent))
        elif path.is_dir():
            yang_files = [
                str(f) for f in sorted(path.rglob("*.yang")) if not _is_external(f)
            ]
            all_files.extend(yang_files)
            search_paths.append(str(path))
            _augment_search_paths(path, search_paths)
        elif path.is_file() and path.suffix == ".yang":
            all_files.append(str(path))
            search_paths.append(str(path.parent))
        else:
            raise ValueError(
                f"Input must be a .yang file, directory, or .zip: {input_path}"
            )

    all_files = list(dict.fromkeys(all_files))
    search_paths = list(dict.fromkeys(search_paths))
    return all_files, search_paths


def _extract_zip(zip_path: Path) -> tuple[list[str], str]:
    """Extract .yang files from a zip to a temp dir, guarding against zip-slip."""
    extract_dir = Path(tempfile.mkdtemp(prefix="yang_to_rdf_"))
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if not member.endswith(".yang"):
                continue
            dest = (extract_dir / member).resolve()
            if not str(dest).startswith(str(extract_dir.resolve()) + os.sep):
                raise ValueError(f"Unsafe path in zip (zip-slip): {member}")
            zf.extract(member, extract_dir)

    yang_files = [
        str(f) for f in sorted(extract_dir.rglob("*.yang")) if not _is_external(f)
    ]
    return yang_files, str(extract_dir)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_input_handler.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/input_handler.py tests/test_input_handler.py
git commit -S -m "input_handler: external-yams search path, zip-slip guard, exclude deps"
```

---

### Task 3: type_resolver — shared type resolution over the typedef chain

**Files:**
- Create: `yang_to_rdf/type_resolver.py`
- Test: `tests/test_type_resolver.py`

**Interfaces:**
- Consumes: `build_context` (Task 1) in tests only.
- Produces:
  - `DN_TYPEDEFS: set[str] = {"DistinguishedName", "Dn", "LDN"}`
  - `@dataclass ResolvedType` with fields: `xsd: URIRef | None`, `enums: list[str]`, `pattern: str | None`, `is_reference: bool`, `datatype_iri: str | None` (IRI of a typedef modeled as `rdfs:Datatype`, else None).
  - `resolve_type(type_stmt) -> ResolvedType` — walks `type_stmt.i_typedef` chain and `i_type_spec`; sets `is_reference=True` when the chain includes any name in `DN_TYPEDEFS`; collects enums/pattern from the resolved spec; maps base builtins via `YANG_TO_XSD`/`IETF_TYPE_MAP`.
  - Module-level `YANG_TO_XSD`, `IETF_TYPE_MAP` dicts (moved here from rdf_converter; rdf_converter will import from here).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_type_resolver.py
import glob, os
from yang_to_rdf.pyang_context import build_context
from yang_to_rdf.type_resolver import resolve_type, DN_TYPEDEFS
from rdflib.namespace import XSD

def _ctx(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    return build_context(files, [yang_dir, external_yams_dir])[0]

def _find_leaf(ctx, module, leaf_name):
    m = ctx.get_module(module)
    stack = list(m.substmts)
    while stack:
        c = stack.pop(); stack += list(c.substmts)
        if c.keyword in ("leaf", "leaf-list") and c.arg == leaf_name:
            return c
    raise AssertionError(f"leaf {leaf_name} not found")

def test_dn_leaf_is_reference(yang_dir, external_yams_dir):
    ctx = _ctx(yang_dir, external_yams_dir)
    leaf = _find_leaf(ctx, "_3gpp-5gc-nrm-amffunction", "aMFSetRef")
    rt = resolve_type(leaf.search_one("type"))
    assert rt.is_reference is True
    assert rt.pattern is not None  # DN pattern carried through

def test_enum_typedef_resolves_enums(yang_dir, external_yams_dir):
    ctx = _ctx(yang_dir, external_yams_dir)
    # a leaf whose type is the CommModelType enum typedef
    m = ctx.get_module("_3gpp-5g-common-yang-types")
    td = m.search_one("typedef", "CommModelType")
    rt = resolve_type(td.search_one("type"))
    assert len(rt.enums) > 0

def test_plain_string_leaf(yang_dir, external_yams_dir):
    ctx = _ctx(yang_dir, external_yams_dir)
    leaf = _find_leaf(ctx, "_3gpp-common-managed-function", "userLabel")
    rt = resolve_type(leaf.search_one("type"))
    assert rt.xsd == XSD.string
    assert rt.is_reference is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_type_resolver.py -v`
Expected: FAIL with import error for `yang_to_rdf.type_resolver`.

- [ ] **Step 3: Write implementation**

```python
# yang_to_rdf/type_resolver.py
"""Shared resolution of YANG types over the resolved typedef chain."""
from __future__ import annotations

from dataclasses import dataclass, field

from rdflib import URIRef
from rdflib.namespace import XSD

DN_TYPEDEFS = {"DistinguishedName", "Dn", "LDN"}

YANG_TO_XSD = {
    "string": XSD.string, "boolean": XSD.boolean,
    "uint8": XSD.unsignedByte, "uint16": XSD.unsignedShort,
    "uint32": XSD.unsignedInt, "uint64": XSD.unsignedLong,
    "int8": XSD.byte, "int16": XSD.short, "int32": XSD.int, "int64": XSD.long,
    "decimal64": XSD.decimal, "empty": XSD.boolean, "binary": XSD.base64Binary,
    "instance-identifier": XSD.anyURI, "union": XSD.string,
}
IETF_TYPE_MAP = {
    "inet:ipv4-address": XSD.string, "inet:ipv6-address": XSD.string,
    "inet:domain-name": XSD.string, "inet:host": XSD.string,
    "inet:host-name": XSD.string, "inet:uri": XSD.anyURI,
    "yang:date-and-time": XSD.dateTime, "yang:hex-string": XSD.string,
    "yang:counter64": XSD.unsignedLong, "yang:gauge64": XSD.unsignedLong,
}


@dataclass
class ResolvedType:
    xsd: URIRef | None = None
    enums: list[str] = field(default_factory=list)
    pattern: str | None = None
    is_reference: bool = False
    datatype_iri: str | None = None
    base_name: str = "string"


def _local(name: str) -> str:
    return name.split(":")[-1] if ":" in name else name


def resolve_type(type_stmt) -> ResolvedType:
    """Walk a leaf's type: follow the typedef chain, collect constraints."""
    rt = ResolvedType()
    if type_stmt is None:
        rt.xsd = XSD.string
        return rt

    # Walk the chain of type statements (leaf -> typedef -> typedef -> builtin).
    chain_names: list[str] = []
    cur = type_stmt
    for _ in range(12):
        chain_names.append(cur.arg)
        # collect enums/pattern from whichever level declares them
        for enum in cur.search("enum"):
            if enum.arg not in rt.enums:
                rt.enums.append(enum.arg)
        pat = cur.search_one("pattern")
        if pat is not None and rt.pattern is None:
            rt.pattern = pat.arg
        td = getattr(cur, "i_typedef", None)
        if td is None:
            break
        nxt = td.search_one("type")
        if nxt is None:
            break
        cur = nxt

    rt.base_name = cur.arg
    if any(_local(n) in DN_TYPEDEFS for n in chain_names):
        rt.is_reference = True

    # Map the base builtin/known type to XSD.
    base = cur.arg
    if base in YANG_TO_XSD:
        rt.xsd = YANG_TO_XSD[base]
    elif base in IETF_TYPE_MAP:
        rt.xsd = IETF_TYPE_MAP[base]
    elif base == "enumeration":
        rt.xsd = XSD.string
    else:
        rt.xsd = XSD.string
    return rt
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_type_resolver.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/type_resolver.py tests/test_type_resolver.py
git commit -S -m "Add shared type_resolver over the resolved typedef chain"
```

---

### Task 4: yang_parser — resolved-tree IR (IOCs, dataType classes, containment)

**Files:**
- Modify (rewrite): `yang_to_rdf/yang_parser.py`
- Test: `tests/test_yang_parser.py`

**Interfaces:**
- Consumes: `build_context` (Task 1), `resolve_type`/`ResolvedType` (Task 3), `class_iri`/`property_iri` (namespace.py, unchanged).
- Produces:
  - `Leaf` — `name, type_name, description, mandatory, is_list, min_elements, max_elements, enums, pattern, xsd, is_reference, is_invariant`.
  - `AttrRef` — a structured (dataType) attribute link: `name: str` (property local name), `target_iri: str` (dataType class IRI), `min_elements: int|None`, `max_elements: int|None`, `description: str`.
  - `Klass` — models both IOCs and dataType classes: `name, namespace, kind` (`"ioc"` | `"datatype"`), `description`, `subclass_of: list[str]` (class IRIs), `leaves: list[Leaf]`, `attr_refs: list[AttrRef]` (nested dataType structures), `contains: list[str]` (child IOC class IRIs — IOC kind only).
  - `Typedef` — `name, namespace, enums, pattern, description`.
  - `Model` — `classes: list[Klass]`, `typedefs: list[Typedef]`. Convenience: `Model.iocs` property → `[c for c in classes if c.kind=="ioc"]`.
  - `parse(yang_files, search_paths) -> tuple[Model, list[str]]`.

**Model rules (verified against the set — see Reference Facts):**
- A schema `list` node is an **IOC** iff its resolved `i_children` contains a `container` named `attributes`. Its class IRI is `class_iri(namespace+"/", list.arg)`.
- Inside an IOC's `attributes` container: `leaf`/`leaf-list` (≠ `idx`) → `Leaf`; a nested `list` → a **dataType class** (`kind="datatype"`), and the IOC gets an `AttrRef(name=list.arg, target_iri=<datatype class IRI>, min/max)`. dataType classes are registered recursively (a dataType may nest further dataType lists inside its own direct children — treat direct `leaf`/`leaf-list` as leaves and direct nested `list` as further dataType attr_refs). dataType class name = the list node's `arg` (e.g. `thresholdInfoList` → class `thresholdInfoList`; do not case-fold — keep the YANG identifier so IRIs stay deterministic and reversible).
- A `list` that is a **sibling** of the `attributes` container (i.e. a direct child of the IOC list, not inside `attributes`) and is itself an IOC → recorded in the parent IOC's `contains` (containment), and registered as its own IOC.
- Inheritance: for an IOC, inspect `uses` both directly on the list node and inside its `attributes` container; if a used grouping resolves (via `i_grouping`, recursively through nested `uses`) to `ManagedFunctionGrp`, add `"https://3gpp.org/nrm/vocab#ManagedFunction"` to `subclass_of`.
- `is_invariant`: read directly from the leaf's `substmts` — true iff any substmt keyword tuple equals `("_3gpp-common-yang-extensions", "inVariant")`. (Verified readable on resolved `i_children`.)
- Seed the walk from every `augment.i_target_node` that is a `list` (containment parents like `ManagedElement`/`SubNetwork`), plus register augment-added child lists. Deduplicate classes by IRI (`seen` dict) — a class reached by multiple paths is registered once.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_yang_parser.py
import glob, os
from yang_to_rdf.yang_parser import parse

def _model(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    return parse(files, [yang_dir, external_yams_dir])

def test_parses_cleanly(yang_dir, external_yams_dir):
    _, errors = _model(yang_dir, external_yams_dir)
    assert errors == []

def test_amffunction_is_ioc_subclass_managed_function(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    amf = next(c for c in model.iocs if c.name == "AMFFunction")
    assert amf.kind == "ioc"
    assert any("ManagedFunction" in s for s in amf.subclass_of)

def test_inherited_leaf_present(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    amf = next(c for c in model.iocs if c.name == "AMFFunction")
    assert "userLabel" in {l.name for l in amf.leaves}

def test_dn_reference_leaf_flagged(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    amf = next(c for c in model.iocs if c.name == "AMFFunction")
    ref = next(l for l in amf.leaves if l.name == "aMFSetRef")
    assert ref.is_reference is True

def test_datatype_modeled_as_class_not_dropped(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    # thresholdInfoList is a MULTIVALUED nested dataType under ThresholdMonitor.attributes
    tm = next(c for c in model.iocs if c.name == "ThresholdMonitor")
    ref = next(a for a in tm.attr_refs if a.name == "thresholdInfoList")
    # its target is a datatype class carrying the structured leaves
    dt = next(c for c in model.classes if c.kind == "datatype"
              and c.name == "thresholdInfoList")
    assert "thresholdValue" in {l.name for l in dt.leaves}

def test_singleton_datatype_also_a_class(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    ausf = next(c for c in model.iocs if c.name == "AUSFFunction")
    ref = next(a for a in ausf.attr_refs if a.name == "ausfInfo")
    dt = next(c for c in model.classes if c.kind == "datatype" and c.name == "ausfInfo")
    inv = next(l for l in dt.leaves if l.name == "nFSrvGroupId")
    assert inv.is_invariant is True

def test_managed_element_contains_amffunction(yang_dir, external_yams_dir):
    model, _ = _model(yang_dir, external_yams_dir)
    me = next(c for c in model.iocs if c.name == "ManagedElement")
    assert any("AMFFunction" in c for c in me.contains)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_yang_parser.py -v`
Expected: FAIL (new API / dataclasses not present).

- [ ] **Step 3: Write implementation**

```python
# yang_to_rdf/yang_parser.py
"""Build an RDF-oriented IR from pyang's *resolved* schema tree."""
from __future__ import annotations

from dataclasses import dataclass, field

from yang_to_rdf.namespace import class_iri
from yang_to_rdf.pyang_context import build_context
from yang_to_rdf.type_resolver import resolve_type

INVARIANT_EXT = ("_3gpp-common-yang-extensions", "inVariant")
MANAGED_FUNCTION_GRP = "ManagedFunctionGrp"
MANAGED_FUNCTION_IRI = "https://3gpp.org/nrm/vocab#ManagedFunction"


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


def _leaf_from(stmt) -> Leaf:
    t = stmt.search_one("type")
    rt = resolve_type(t)
    mand = stmt.search_one("mandatory")
    return Leaf(
        name=stmt.arg,
        type_name=t.arg if t is not None else "string",
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

    def _register_datatype(self, list_node) -> str:
        """Register a nested dataType list as a class; return its IRI."""
        ns = _ns(list_node)
        iri = class_iri(ns + "/", list_node.arg)
        if iri in self.seen:
            return iri
        cls = Klass(name=list_node.arg, namespace=ns, kind="datatype",
                    description=_desc(list_node))
        self.seen[iri] = cls
        self.model.classes.append(cls)
        self._fill_children(cls, list_node)
        return iri

    def _fill_children(self, cls: Klass, node) -> None:
        """Populate leaves + nested dataType attr_refs from a node's direct children."""
        for c in getattr(node, "i_children", []):
            if c.keyword in ("leaf", "leaf-list") and c.arg != "idx":
                cls.leaves.append(_leaf_from(c))
            elif c.keyword == "list":
                target = self._register_datatype(c)
                cls.attr_refs.append(AttrRef(
                    name=c.arg, target_iri=target,
                    min_elements=_int(c, "min-elements"),
                    max_elements=_int(c, "max-elements"),
                    description=_desc(c),
                ))

    def register_ioc(self, list_node) -> Klass:
        ns = _ns(list_node)
        iri = class_iri(ns + "/", list_node.arg)
        existing = self.seen.get(iri)
        if existing is not None and existing.kind == "ioc":
            return existing
        cls = Klass(name=list_node.arg, namespace=ns, kind="ioc",
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
        for c in getattr(list_node, "i_children", []):
            if c.keyword == "list" and c.arg != "idx":
                child = self.register_ioc(c)
                child_iri = class_iri(child.namespace + "/", child.name)
                if child_iri not in cls.contains:
                    cls.contains.append(child_iri)
        return cls

    def run(self, ctx):
        for m in ctx.modules.values():
            if m.keyword != "module":
                continue
            for td in m.search("typedef"):
                rt = resolve_type(td.search_one("type"))
                self.model.typedefs.append(
                    Typedef(td.arg, _ns(m), rt.enums, rt.pattern, _desc(td)))

        for m in ctx.modules.values():
            if m.keyword != "module":
                continue
            for aug in m.search("augment"):
                tgt = getattr(aug, "i_target_node", None)
                if tgt is None or tgt.keyword != "list":
                    continue
                parent = self.register_ioc(tgt)
                for child in getattr(aug, "i_children", []):
                    if child.keyword == "list" and child.arg != "idx":
                        child_ioc = self.register_ioc(child)
                        ci = class_iri(child_ioc.namespace + "/", child_ioc.name)
                        if ci not in parent.contains:
                            parent.contains.append(ci)
        return self.model


def parse(yang_files, search_paths) -> tuple[Model, list[str]]:
    ctx, errors = build_context(yang_files, search_paths)
    model = _Parser().run(ctx)
    return model, errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_yang_parser.py -v`
Expected: PASS (all 7). If a class is reached first as a dataType then later as an IOC (or vice versa), the `seen` dedup keeps the first; the tests above do not hit that case. If one genuinely does, report it — do not weaken an assertion.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/yang_parser.py tests/test_yang_parser.py
git commit -S -m "Rewrite yang_parser on resolved tree: IOCs, dataType classes, containment, inheritance"
```

---

### Task 5: rdf_converter — base TBox (IOCs + dataType classes)

**Files:**
- Modify (rewrite): `yang_to_rdf/rdf_converter.py`
- Test: `tests/test_rdf_converter.py`

**Interfaces:**
- Consumes: `Model`/`Klass`/`Leaf`/`AttrRef`/`Typedef` (Task 4), `class_iri`/`property_iri` (namespace.py).
- Produces: `class YangToRDFConverter(model: Model)` with `.convert() -> rdflib.Graph`. Module constant `NRM = Namespace("https://3gpp.org/nrm/vocab#")`. New term `NRM.hasAttribute` (object property linking an IOC/dataType to a nested dataType class).

**Emission rules:**
- Every `Klass` (ioc and datatype) → `rdfs:Class` with `rdfs:comment` from description.
- `subclass_of` → `rdfs:subClassOf`.
- `contains` (IOC only) → `nrm:nameContains` to each child IOC class.
- `attr_refs` → for each, an `owl:ObjectProperty` `property_iri(base, cls, attr.name)` with `rdfs:domain` = the class and `rdfs:range` = the dataType class IRI, plus `nrm:hasAttribute` from class to the dataType class.
- Leaves: DN reference (`is_reference`) → `owl:ObjectProperty` + `nrm:isReference true`, range left open; else `rdf:Property` with `rdfs:range` = `leaf.xsd`. `rdfs:domain` = the class. `is_invariant` → `nrm:isInvariant true`.
- Typedefs → `rdfs:Datatype` (not `rdfs:Class`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rdf_converter.py
import glob, os
from rdflib import RDF, RDFS, Literal, URIRef
from rdflib.namespace import OWL
from yang_to_rdf.yang_parser import parse
from yang_to_rdf.rdf_converter import YangToRDFConverter, NRM

def _graph(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    model, _ = parse(files, [yang_dir, external_yams_dir])
    return YangToRDFConverter(model).convert()

AMF = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction")

def test_amffunction_is_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    assert (AMF, RDF.type, RDFS.Class) in g

def test_amffunction_subclass_managed_function(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    assert (AMF, RDFS.subClassOf, NRM.ManagedFunction) in g

def test_datatype_is_class_and_linked(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    tm = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/ThresholdMonitor")
    dt = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/thresholdInfoList")
    assert (dt, RDF.type, RDFS.Class) in g
    prop = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/ThresholdMonitor/thresholdInfoList")
    assert (prop, RDF.type, OWL.ObjectProperty) in g
    assert (prop, RDFS.range, dt) in g
    assert (prop, RDFS.domain, tm) in g

def test_dn_ref_is_object_property_without_range(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    ref = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction/aMFSetRef")
    assert (ref, RDF.type, OWL.ObjectProperty) in g
    assert (ref, NRM.isReference, Literal(True)) in g
    assert list(g.objects(ref, RDFS.range)) == []

def test_typedef_is_datatype_not_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    dn = URIRef("urn:3gpp:sa5:_3gpp-common-yang-types/DistinguishedName")
    assert (dn, RDF.type, RDFS.Datatype) in g
    assert (dn, RDF.type, RDFS.Class) not in g
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rdf_converter.py -v`
Expected: FAIL (module/behavior not present).

- [ ] **Step 3: Write implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rdf_converter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/rdf_converter.py tests/test_rdf_converter.py
git commit -S -m "Rewrite rdf_converter: IOC + dataType classes, hasAttribute, DN object props, datatypes"
```

---

### Task 6: shacl_converter — shapes for IOCs and dataType classes

**Files:**
- Modify (rewrite): `yang_to_rdf/shacl_converter.py`
- Test: `tests/test_shacl_converter.py`

**Interfaces:**
- Consumes: `Model`/`Klass`/`Leaf`/`AttrRef` (Task 4), `NRM` (Task 5), `class_iri`/`property_iri`.
- Produces: `class YangToSHACLConverter(model: Model)` with `.convert() -> Graph`. `SH = Namespace("http://www.w3.org/ns/shacl#")`.

**Emission rules:**
- One `sh:NodeShape` per `Klass` (ioc and datatype), `sh:targetClass` = the class IRI, shape IRI = `class_iri(base, name+"Shape")`.
- Each `Leaf` → a `sh:property` blank node: `sh:path` = property IRI; `sh:datatype` = `leaf.xsd` unless it has enums or is a reference; `sh:minCount 1` if mandatory (else from `min_elements`); `sh:maxCount 1` unless `is_list` (else from `max_elements`); `sh:in` for enums; `sh:pattern` for pattern; `sh:description`.
- Each `AttrRef` → a `sh:property` blank node: `sh:path` = property IRI; `sh:class` = `attr.target_iri`; `sh:minCount`/`sh:maxCount` from min/max; `sh:description`.
- Because the IR already materializes inherited leaves onto each IOC, no `subClassOf` walking is needed — shapes are self-contained.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shacl_converter.py
import glob, os
from rdflib import RDF, URIRef
from yang_to_rdf.yang_parser import parse
from yang_to_rdf.shacl_converter import YangToSHACLConverter, SH

def _graph(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    model, _ = parse(files, [yang_dir, external_yams_dir])
    return YangToSHACLConverter(model).convert()

AMF_SHAPE = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunctionShape")
AMF = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction")

def test_shape_targets_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    assert (AMF_SHAPE, RDF.type, SH.NodeShape) in g
    assert (AMF_SHAPE, SH.targetClass, AMF) in g

def test_inherited_property_materialized(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    paths = {str(p) for ps in g.objects(AMF_SHAPE, SH.property)
             for p in g.objects(ps, SH.path)}
    assert any(p.endswith("/AMFFunction/userLabel") for p in paths)

def test_datatype_attr_uses_sh_class(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    tm_shape = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/ThresholdMonitorShape")
    dt = URIRef("urn:3gpp:sa5:_3gpp-common-managed-element/thresholdInfoList")
    classes = set()
    for ps in g.objects(tm_shape, SH.property):
        for c in g.objects(ps, SH["class"]):
            classes.add(c)
    assert dt in classes

def test_dn_pattern_present(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    patterns = [str(o) for o in g.objects(None, SH.pattern)]
    assert any("=" in p for p in patterns)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_shacl_converter.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

```python
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
        for leaf in cls.leaves:
            self._emit_leaf_shape(shape, leaf, cls, base)
        for ref in cls.attr_refs:
            self._emit_attr_shape(shape, ref, cls, base)

    def _emit_leaf_shape(self, shape, leaf: Leaf, cls: Klass, base: str):
        g = self.graph
        ps = BNode()
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
            lst = BNode()
            Collection(g, lst, [Literal(e) for e in leaf.enums])
            g.add((ps, SH["in"], lst))
        if leaf.pattern:
            g.add((ps, SH.pattern, Literal(leaf.pattern)))
        if leaf.description:
            g.add((ps, SH.description, Literal(leaf.description)))

    def _emit_attr_shape(self, shape, ref: AttrRef, cls: Klass, base: str):
        g = self.graph
        ps = BNode()
        g.add((shape, SH.property, ps))
        g.add((ps, SH.path, URIRef(property_iri(base, cls.name, ref.name))))
        g.add((ps, SH["class"], URIRef(ref.target_iri)))
        if ref.min_elements:
            g.add((ps, SH.minCount, Literal(ref.min_elements)))
        if ref.max_elements is not None:
            g.add((ps, SH.maxCount, Literal(ref.max_elements)))
        if ref.description:
            g.add((ps, SH.description, Literal(ref.description)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_shacl_converter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/shacl_converter.py tests/test_shacl_converter.py
git commit -S -m "Rewrite shacl_converter: IOC + dataType shapes, sh:class links, DN pattern"
```

---

### Task 7: reference_layer — auditable inferred-range extension graph

**Files:**
- Create: `yang_to_rdf/reference_layer.py`
- Test: `tests/test_reference_layer.py`

**Interfaces:**
- Consumes: `Model`/`Klass`/`Leaf` (Task 4), `NRM` (Task 5), `class_iri`/`property_iri`.
- Produces: `class ReferenceLayerBuilder(model: Model)` with `.build() -> Graph`. Provenance predicates `NRM.inferredBy`, `NRM.confidence`, `NRM.candidate`. Confidence values `"unambiguous"` / `"unresolved"`. Class-name inference: strip trailing `RefList`/`Refs`/`Ref`/`List`, capitalize first char; unambiguous iff the candidate matches exactly one IOC name in the model.

**Rules:**
- Iterate all classes (ioc + datatype); for each `is_reference` leaf, emit provenance. Match the stripped+capitalized candidate against IOC names only (`kind=="ioc"`). Exactly one match → `rdfs:range` = that class IRI + `nrm:confidence "unambiguous"`. No match → `nrm:confidence "unresolved"` + `nrm:candidate` (the guessed name), no range. Always `nrm:inferredBy "dn-name-suffix"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reference_layer.py
import glob, os
from rdflib import RDFS, URIRef, Literal
from yang_to_rdf.yang_parser import parse
from yang_to_rdf.reference_layer import ReferenceLayerBuilder
from yang_to_rdf.rdf_converter import NRM

def _graph(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    model, _ = parse(files, [yang_dir, external_yams_dir])
    return ReferenceLayerBuilder(model).build()

def test_unambiguous_range_inferred(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    ref = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction/aMFSetRef")
    ranges = list(g.objects(ref, RDFS.range))
    assert any(str(r).endswith("/AMFSet") for r in ranges)
    assert (ref, NRM.confidence, Literal("unambiguous")) in g

def test_unresolved_ref_listed_not_dropped(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    subj = [s for s in g.subjects(NRM.confidence, Literal("unresolved"))
            if str(s).endswith("_5GCNFRef")]
    assert subj, "unresolved DN ref must be recorded, not silently dropped"
    assert list(g.objects(subj[0], RDFS.range)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reference_layer.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reference_layer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add yang_to_rdf/reference_layer.py tests/test_reference_layer.py
git commit -S -m "Add auditable reference_layer: inferred DN ranges with provenance"
```

### Task 8: main.py wiring + determinism + README

**Files:**
- Modify: `yang_to_rdf/main.py`
- Modify: `README.md`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: everything above.
- Produces: CLI that writes `<stem>_rdf.ttl`, `<stem>_shacl.ttl`, and (unless `--no-inference`) `<stem>_refs.ttl`. `parse` is called once; both converters + reference layer share the `Model`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main.py
import glob, os, subprocess, sys
from pathlib import Path

def test_cli_emits_three_layers_and_is_deterministic(yang_dir, external_yams_dir, tmp_path):
    out1 = tmp_path / "o1"; out2 = tmp_path / "o2"
    cmd = [sys.executable, "-m", "yang_to_rdf.main", yang_dir, "-o"]
    subprocess.run(cmd + [str(out1)], check=True)
    subprocess.run(cmd + [str(out2)], check=True)
    stem = Path(yang_dir).name
    for suffix in ("_rdf.ttl", "_shacl.ttl", "_refs.ttl"):
        f1 = out1 / f"{stem}{suffix}"
        assert f1.is_file(), f"missing {suffix}"
        # deterministic across runs
        assert f1.read_bytes() == (out2 / f"{stem}{suffix}").read_bytes()

def test_no_inference_skips_refs(yang_dir, tmp_path):
    out = tmp_path / "o"
    subprocess.run(
        [sys.executable, "-m", "yang_to_rdf.main", yang_dir, "-o", str(out),
         "--no-inference"], check=True)
    stem = Path(yang_dir).name
    assert not (out / f"{stem}_refs.ttl").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL (no refs layer / `--no-inference` unknown / `python -m` entry).

- [ ] **Step 3: Write implementation**

```python
# yang_to_rdf/main.py
"""CLI entry point for yang-to-rdf."""
import argparse
import os
import sys
from pathlib import Path

from yang_to_rdf.input_handler import collect_yang_files
from yang_to_rdf.rdf_converter import YangToRDFConverter
from yang_to_rdf.reference_layer import ReferenceLayerBuilder
from yang_to_rdf.shacl_converter import YangToSHACLConverter
from yang_to_rdf.yang_parser import parse


def main():
    p = argparse.ArgumentParser(
        description="Convert a complete 3GPP YANG module set to RDF TBox + SHACL shapes",
        epilog="Example: yang-to-rdf MnS-Rel-19-yang-models.zip",
    )
    p.add_argument("input", nargs="+", help="Path(s) to .yang, directory, or .zip")
    p.add_argument("--format", choices=["rdf", "shacl", "both"], default="both")
    p.add_argument("--no-inference", action="store_true",
                   help="Skip the reference extension layer (<stem>_refs.ttl)")
    p.add_argument("--output", "-o", default="output")
    p.add_argument("--version", action="version", version="%(prog)s 0.2.0")
    args = p.parse_args()

    try:
        yang_files, search_paths = collect_yang_files(args.input)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if not yang_files:
        print("No .yang files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(yang_files)} YANG files")
    model, errors = parse(yang_files, search_paths)
    if errors:
        print(f"WARNING: {len(errors)} validation error(s); output may be incomplete:",
              file=sys.stderr)
        for e in errors[:10]:
            print(f"  {e}", file=sys.stderr)
    print(f"Parsed {len(model.iocs)} IOCs, {len(model.typedefs)} typedefs")

    os.makedirs(args.output, exist_ok=True)
    stem = Path(args.input[0]).stem

    if args.format in ("rdf", "both"):
        g = YangToRDFConverter(model).convert()
        path = os.path.join(args.output, f"{stem}_rdf.ttl")
        g.serialize(destination=path, format="turtle")
        print(f"RDF TBox -> {path} ({len(g)} triples)")

    if args.format in ("shacl", "both"):
        g = YangToSHACLConverter(model).convert()
        path = os.path.join(args.output, f"{stem}_shacl.ttl")
        g.serialize(destination=path, format="turtle")
        print(f"SHACL shapes -> {path} ({len(g)} triples)")

    if not args.no_inference:
        g = ReferenceLayerBuilder(model).build()
        path = os.path.join(args.output, f"{stem}_refs.ttl")
        g.serialize(destination=path, format="turtle")
        print(f"Reference layer -> {path} ({len(g)} triples)")

    print("Done.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_main.py -v`
Expected: PASS. (rdflib turtle serialization is canonical/sorted, so byte-equality across runs holds.)

- [ ] **Step 5: Update README**

Replace the Usage and Design sections of `README.md` so all examples use the complete set (`MnS-Rel-19-yang-models.zip`), document the three output files (`_rdf.ttl`, `_shacl.ttl`, `_refs.ttl`), the `--no-inference` flag, that the input must be a complete set with its `external-yams/` folder, and where to obtain modules (`https://forge.3gpp.org/rep/sa5/MnS`). Remove all `28541-k20.zip` references. Add the DN-reference / extension-layer explanation from the design's DN section.

- [ ] **Step 6: Commit**

```bash
git add yang_to_rdf/main.py README.md tests/test_main.py
git commit -S -m "Wire CLI to three-layer output, surface errors, deterministic; update README"
```

---

### Task 9: cleanup — remove dead code, update pyproject, full run

**Files:**
- Modify: `yang_to_rdf/namespace.py` (verify unchanged API; no edit expected)
- Modify: `pyproject.toml` (add pytest dev dependency; bump version to 0.2.0)
- Delete: any leftover references to removed symbols

**Interfaces:**
- Consumes: everything.
- Produces: a clean `uv run pytest` (all green) and a real end-to-end run over the full set.

- [ ] **Step 1: Add pytest as dev dependency + bump version**

In `pyproject.toml`, set `version = "0.2.0"` and add:

```toml
[dependency-groups]
dev = ["pytest>=8.0"]
```

- [ ] **Step 2: Run the entire suite**

Run: `uv run pytest -v`
Expected: all tests PASS, no skips (zip present at repo root).

- [ ] **Step 3: Real end-to-end run**

Run: `uv run yang-to-rdf MnS-Rel-19-yang-models.zip -o output/v4`
Expected: prints IOC/typedef counts, writes `output/v4/MnS-Rel-19-yang-models_rdf.ttl`, `_shacl.ttl`, `_refs.ttl`; no validation-error warning (complete set).

- [ ] **Step 4: Sanity-diff against old output**

Run: `grep -c "a rdfs:Class" output/v4/MnS-Rel-19-yang-models_rdf.ttl` and compare IOC count is in a sane range (dozens+). Confirm `_refs.ttl` contains both `"unambiguous"` and `"unresolved"` confidence values:
Run: `grep -c unambiguous output/v4/*_refs.ttl && grep -c unresolved output/v4/*_refs.ttl`
Expected: 121 unambiguous, ~494 unresolved (unambiguous = DN candidate names unique among IOCs).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -S -m "Bump to 0.2.0, add pytest dev dependency"
```

---

## Self-Review Notes

- **Spec coverage:** dataset/external-yams (Task 2), resolved-tree parser + heuristic deletion (Task 4), error surfacing (Tasks 1, 8), typedef→Datatype + shared resolver (Tasks 3, 5), DN object property + open range (Task 5), extension layer with tiers/provenance (Task 7), inVariant (Tasks 4, 5), SHACL inheritance materialization (Task 6), zip-slip/cleanup (Task 2), tests (all), README/CLI (Task 8). identityref explicitly deferred per spec Non-Goals. Covered.
- **Type consistency:** `parse() -> (Model, list[str])`, `Model.classes` + `Model.iocs` property, `Klass.kind/leaves/attr_refs/subclass_of/contains/namespace`, `AttrRef.name/target_iri/min_elements/max_elements`, `Leaf.is_reference/is_invariant/xsd`, converters take `model` positionally, `NRM` (incl. `hasAttribute`) imported from rdf_converter by shacl_converter and reference_layer — consistent across tasks.
- **Placeholders:** none; all steps carry real code/commands and verified reference facts.
- **Risk note:** Task 4's IOC-discovery seeding is the highest-risk step (depends on augment `i_target_node`/`i_children` shape). It is tested first (Task 4 Step 1) exactly so a surprise surfaces there, before Tasks 5–8 build on it — matching the "no dead-ends" goal.
