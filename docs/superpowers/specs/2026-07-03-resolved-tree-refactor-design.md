# yang-to-rdf: Resolved-Tree Refactor — Design

Date: 2026-07-03
Branch: `resolved-tree-refactor`
Status: Approved

## Problem

The current parser walks pyang's **raw** statement tree and reconstructs YANG's
resolution semantics with string heuristics tuned to 3GPP naming conventions
(`_identify_ioc_groupings`, `endswith("Grp")` inheritance, `_resolve_augment_target`
IRI-minting fallback). These heuristics exist because the tool was run against an
**incomplete** module set (`28541-k20.zip`), where pyang cannot resolve imports,
augments, or `uses` (299 swallowed validation errors; augment targets unresolved).

Empirically, given a **complete** set, pyang's *resolved* tree provides the real
answers for free:

- `MnS-Rel-19-yang-models.zip` (with its bundled `yang-models/external-yams/`
  folder) validates with **0 errors, 118 modules**.
- `augment.i_target_node` resolves cross-module; augmented IOCs appear in the
  target's `i_children` (real containment).
- `uses ManagedFunctionGrp` expands cross-module into `i_children` (real
  inheritance; `userLabel`/`priorityLabel` confirmed present on `AMFFunction`).
- Typedef constraints are reachable via `type.i_type_spec` / `i_typedef` chains.

libyang `lysc` was evaluated and rejected: 3GPP NRM uses 0 leafref, 6 deviation
stmts, 2 identities — the constructs where lysc beats pyang barely apply, and it
adds a C dependency. pyang's resolved tree is sufficient.

## Goals

1. Make pyang's resolved tree the single source of truth; delete the heuristics.
2. Convert only what is unambiguous into the base RDF/SHACL output.
3. Emit inferred/heuristic mappings into a **separate, auditable extension layer**,
   never buried in the base conversion and never silently dropped.
4. Add a test suite (currently zero tests).

## Non-Goals

- `identityref` → `rdfs:subClassOf` (only 2 3GPP identities; deferred, YAGNI).
- DN target-class inference in the base layer (unreliable; lives in extension layer).
- Supporting incomplete module sets as a first-class mode (they now warn loudly).

## Dataset & Input

- The tool targets a **complete** 3GPP SA5 module set. `MnS-Rel-19-yang-models.zip`
  is the reference set, copied to the repo root and git-ignored (`*.zip`).
- `28541-k20.zip` (incomplete) is no longer a supported/example input.
- `input_handler`:
  - When extracting/scanning, detect an `external-yams/` subfolder and add it to
    the pyang search path. External modules ship inside the set — nothing to download.
  - **Never** add pyang's own bundled IETF modules to the search path (they pull in
    `iana-*` modules the 3GPP set does not need, producing spurious errors).
  - Add a zip-slip guard in `_extract_zip` (reject members whose resolved path
    escapes the extraction dir) and clean up the temp directory after use.

## Architecture

Pipeline stages, each an independently testable unit:

```
input_handler → yang_parser (resolved IR) → { rdf_converter, shacl_converter } base graphs
                                           → reference_layer (extension graph)
```

### yang_parser.py (full rewrite)

- Build the dataclass IR from the **resolved** tree: `module.i_children`,
  `module.i_typedefs`, augments via `augment.i_target_node`, and resolved type
  info via `type.i_type_spec` / `i_typedef`.
- Delete `_identify_ioc_groupings`, `endswith("Grp")` inheritance logic, and
  `_resolve_augment_target`'s minting fallback.
- Replace hand-rolled `_Opts` with pyang's real options object; keep only needed
  overrides.
- **Surface errors**: after `ctx.validate()`, if `ctx.errors` contains any tag
  worse than `UNUSED_IMPORT`, print a clear warning with per-tag counts. Do not
  silently degrade.
- **Type resolution**: follow the typedef chain to its base spec so typedef enums,
  patterns, and ranges reach the IR. Expose a single shared type resolver used by
  both converters (fixes the current RDF-vs-SHACL disagreement where SHACL returned
  `None` for typedefs).
- **inVariant**: read `yext3gpp:inVariant` from the **authored grouping source**
  (extensions are stripped from expanded `i_children` copies) and attach to the IR leaf.
- **DN detection**: mark a leaf as a reference when its resolved type chain bottoms
  out at `DistinguishedName` / `Dn` / `LDN`. This is robust and name-independent.

### rdf_converter.py (adapt)

- IOCs → `rdfs:Class`; containment from resolved augments (`nrm:nameContains`);
  inheritance from expanded `uses` (`rdfs:subClassOf`).
- Typedefs → `rdfs:Datatype` when they are value types (not `rdfs:Class`).
- Leaves → properties with correct XSD / typedef-datatype ranges.
- DN leaves → `owl:ObjectProperty` marked `nrm:isReference`, **range left open**.
- `inVariant` leaves → `nrm:isInvariant true` annotation.

### shacl_converter.py (adapt)

- Use the shared type resolver (typedef constraints now flow through).
- **Materialize inherited properties** directly onto each `sh:NodeShape` (the
  resolved tree already gives the fully-expanded attribute list per IOC). No
  `sh:node` composition.
- DN leaves: keep the `DistinguishedName` pattern as `sh:pattern`.

### reference_layer.py (new) — extension graph

Emitted to `<stem>_refs.ttl`, separate from base output:

- **Unambiguous** DN refs (40/96): leaf name ends `Ref`/`RefList`, and
  strip-suffix + capitalize yields a class that **exists** in the emitted vocabulary
  → emit `<property> rdfs:range <inferredClass>` with provenance:
  `nrm:inferredBy "dn-name-suffix"`, `nrm:confidence "unambiguous"`, and the source
  leaf name.
- **Ambiguous** DN refs (56/96): 32 not `Ref`-named, 24 `Ref`-named with no class
  match → emit as `nrm:confidence "unresolved"` worklist entries (property + best-guess
  candidate). Logged, never hidden.
- Loading base + extension together yields ranges; base alone is the honest,
  target-free vocabulary.

### CLI (main.py)

- `--format` continues to control rdf/shacl/both; the extension layer is emitted
  alongside by default.
- New `--no-inference` flag suppresses the extension layer.
- Examples in `--help` and README use the full set, not `28541-k20.zip`.

## IRI Strategy

Unchanged: class = `<module-namespace>/ClassName`, property =
`<module-namespace>/ClassName/propertyName` (path-scoped). New `nrm:` terms:
`nrm:isReference`, `nrm:isInvariant`, plus extension-layer provenance predicates
`nrm:inferredBy`, `nrm:confidence`.

## Testing (TDD)

New `tests/` (pytest, `testpaths = ["tests"]` already configured). Executed
test-first per unit. Run against the full set (fast enough). A session-scoped
fixture parses the set once.

Characterization / behavior tests:
- `AMFFunction` is `nrm:nameContains`-ed by `ManagedElement`.
- `AMFFunction rdfs:subClassOf nrm:ManagedFunction`.
- Inherited `userLabel` / `priorityLabel` appear on `AMFFunction`.
- Enum typedef (`CommModelType`) → `sh:in`; pattern typedef (`UTC24TimeOfDayT`) → `sh:pattern`.
- Typedef → `rdfs:Datatype` (not `rdfs:Class`).

DN / extension layer:
- `aMFSetRef` is an `owl:ObjectProperty` with `nrm:isReference` and **no** `rdfs:range` in base.
- Extension layer has `aMFSetRef rdfs:range …AMFSet` with `nrm:confidence "unambiguous"`.
- `_5GCNFRef` appears in the extension layer as `nrm:confidence "unresolved"`.

Robustness:
- Incomplete set → error-surfacing warning is emitted.
- Determinism: two runs produce byte-identical `.ttl`.
- Zip-slip: a crafted member path is rejected.

## Modules Touched

- `input_handler.py` — external-yams search path, zip-slip guard, cleanup.
- `yang_parser.py` — full rewrite (resolved tree, error surfacing, real opts, type chain, inVariant, DN detection).
- `rdf_converter.py` — adapt; DN object properties; inVariant; typedef datatypes; shared resolver.
- `shacl_converter.py` — adapt; inheritance materialization; shared resolver.
- `reference_layer.py` — **new**; extension graph with provenance.
- `main.py` — `--no-inference`, updated examples.
- `tests/` — **new** suite.
- `README.md`, `.gitignore` — updated.

## Risks

- pyang internal-API drift (`i_children` etc.) — mitigated by tests over the full set.
- Extension-layer name-matching must validate candidates against the **emitted**
  class set (not a static list) so "unambiguous" stays accurate as the vocabulary changes.
