# YANG → RDF conversion notes: decisions, deviations, and where we are non-standard

This document is for reviewers who know YANG and/or RDF/OWL/SHACL and want to
audit **exactly where this tool follows the standards and where it introduces
its own conventions.** YANG and RDF are different modelling worlds; converting
between them forces choices that no standard fully dictates. Everything
non-standard the tool emits is enumerated here.

The short version:

- **Standard vocabularies do the heavy lifting.** Classes, properties, datatypes,
  subclassing, cardinality, patterns, enumerations, and ontology versioning are
  all expressed with `rdf:`, `rdfs:`, `owl:`, `xsd:`, and `sh:` (SHACL) — nothing
  invented.
- **One small project vocabulary, `nrm:`**, carries the handful of 3GPP-specific
  relationships that have no direct standard equivalent. It is namespaced under
  `https://3gpp.org/nrm/vocab#` and is the *entire* non-standard surface. Every
  term is listed below with its justification.
- **No reasoner-dependent semantics are asserted** (no `owl:inverseOf`,
  `owl:disjointWith`, domain/range as OWL restrictions used for inference). RDFS
  `domain`/`range` are used descriptively, and constraints are pushed into SHACL,
  which is closed-world and validation-oriented — the right fit for schema data.

---

## 1. The `nrm:` vocabulary — the complete non-standard surface

Base: `https://3gpp.org/nrm/vocab#`. These are the only terms the tool mints
outside standard vocabularies.

| Term | Declared as | Purpose | Why not a standard term |
|---|---|---|---|
| `nrm:ManagedFunction` | `rdfs:Class` | Common superclass for network-function IOCs (those whose YANG grouping `uses ManagedFunctionGrp`). | 3GPP domain concept; no standard class means "managed function". |
| `nrm:nameContains` | `owl:ObjectProperty` | 3GPP **name-containment** hierarchy — the parent→child structure a DN path encodes (e.g. `SubNetwork` contains `ManagedElement` contains `AMFFunction`). Emitted from YANG `augment`/nested-list structure. | This is 3GPP's specific containment relation, distinct from `rdfs:subClassOf` (that's inheritance) and from generic part-of vocabularies; naming it explicitly keeps it unambiguous. |
| `nrm:hasAttribute` | `owl:ObjectProperty` | Links an IOC (or dataType) to a **structured `<<dataType>>` attribute class** built from a nested `list` inside an `attributes` container. | Distinguishes "a structured attribute value" from `nrm:nameContains` (a contained managed object) — a real 3GPP modelling distinction that no standard predicate captures. |
| `nrm:isReference` | `owl:ObjectProperty`* | Marks a property whose YANG type is a `DistinguishedName` (a reference to another object) rather than a literal value. | See §3 — DN references have no schema-declared target, so we flag them rather than fabricate a `rdfs:range`. |
| `nrm:isInvariant` | `owl:DatatypeProperty`* | Marks a property carrying the 3GPP `yext3gpp:inVariant` extension (set-once / immutable after creation). | 3GPP YANG extension with no OWL/SHACL equivalent; preserved as an annotation so the semantics aren't lost. |

\* `nrm:isReference` and `nrm:isInvariant` are used as **annotation flags** on
properties (object of `true`), not as relationships between individuals. They are
declared with an `owl:` property type for tooling convenience; treat them as
boolean markers, not as assertions requiring OWL reasoning.

### Reference-layer predicates (in `*_refs.ttl` only)

These appear **only** in the separate, opt-out reference-inference layer and are
provenance for a heuristic (see §3):

| Term | Value | Meaning |
|---|---|---|
| `nrm:confidence` | `"unambiguous"` / `"unresolved"` | Whether the inferred range is trusted. |
| `nrm:inferredBy` | `"dn-name-suffix"` | Which heuristic produced the guess. |
| `nrm:candidate` | string | The guessed target class name when unresolved. |

> **Known gap (audit note):** these three reference-layer predicates are currently
> *used* but **not formally declared** (no `rdf:type`/`rdfs:comment` triple) in the
> emitted vocabulary, unlike the five core `nrm:` terms which are declared in the
> base RDF layer. They are provenance annotations, so this is low-impact, but a
> strict OWL consumer will see undeclared predicates. Declaring them is a
> reasonable future improvement.

---

## 2. YANG construct → RDF mapping (and the judgement calls)

| YANG construct | RDF output | Standard? | Note |
|---|---|---|---|
| `module` | `owl:Ontology` (per-module) + `owl:imports` in `index.ttl` | standard | IRI = the module's YANG `namespace` URN. |
| `list` with an `attributes` container (an IOC) | `rdfs:Class` | standard | "Is it an IOC?" is decided structurally (presence of `attributes`), not by name. |
| `list` inside `attributes` (a `<<dataType>>`) | `rdfs:Class` + `nrm:hasAttribute` link | **deviation** | 3GPP structured attributes become first-class classes rather than blank nodes — see §4. |
| `uses <X>Grp` (grouping) | class **named/identified by the grouping** | **deviation** | See §5 — this is the most opinionated choice. |
| `uses ManagedFunctionGrp` | `rdfs:subClassOf nrm:ManagedFunction` | standard use, project class | Inheritance. |
| `augment` / nested sub-IOC list | `nrm:nameContains` | project predicate | Containment (§1). |
| `leaf` | `rdf:Property` + `rdfs:domain` + `rdfs:range` (XSD) | standard | Range from the resolved type chain. |
| `leaf` typed `DistinguishedName`/`Dn`/`LDN` | `owl:ObjectProperty` + `nrm:isReference`, **no `rdfs:range`** | **deviation** | §3. |
| `typedef` | `rdfs:Datatype` | standard | Not `rdfs:Class` — a typedef is a value type. |
| `enumeration` | `sh:in` list in SHACL | standard | Values constrained in the shape, not as individuals. |
| `pattern`, `min/max-elements`, `mandatory` | `sh:pattern` / `sh:minCount` / `sh:maxCount` | standard | Constraints live in SHACL. |
| `choice` / `case` | leaves **flattened onto the owning class** | **deviation / known limitation** | §6 — mutual-exclusivity is currently *not* expressed (`sh:xone` not emitted). |
| `container` (non-`attributes`, nested) | leaves flattened onto the owning class | deviation | Single-instance structured group; no separate class minted. |
| `anydata` / `anyxml` | `rdf:Property` with **open range** | pragmatic | Opaque content has no schema type; we emit the property but assert no range. |
| `revision` | `owl:versionInfo` on the module ontology | standard | See VERSIONING.md. |

---

## 3. DistinguishedName references — why we don't assert a range

A YANG `leafref` names its target (`path`), so a converter could give it a precise
`rdfs:range`. But 3GPP NRM barely uses `leafref`; cross-object references are
**`DistinguishedName`-typed leaves** — an opaque string with **no
schema-declared target class**.

Decision:
- **Detection is reliable and type-based:** a leaf is a reference iff its resolved
  type chain bottoms out at `DistinguishedName`/`Dn`/`LDN`. We mark it
  `nrm:isReference` and, crucially, emit **no `rdfs:range`** in the base ontology —
  asserting a range we cannot justify would be fabrication.
- **Range *inference* is a separate, opt-out layer** (`*_refs.ttl`). It guesses the
  target by stripping a `Ref`/`RefList`/… suffix from the leaf name and matching
  against class names, tagged with `nrm:confidence`. This is explicitly a
  heuristic, physically separated from the base TBox, and labelled as such so a
  consumer can ignore it or audit every guess.

This separation is the deliberate design: **the base ontology contains only what
the schema states; anything inferred is quarantined and provenance-tagged.**

---

## 4. Structured attributes as classes (not blank nodes)

3GPP `<<dataType>>` attributes (a nested `list` inside `attributes`) could be
modelled as anonymous/blank-node structures. We instead mint a **named
`rdfs:Class`** and link it with `nrm:hasAttribute`.

Rationale: these are reused, named 3GPP data types (e.g. `GeoArea`, `PLMNInfo`)
that appear across many IOCs. Giving them stable class IRIs makes the reuse
explicit and queryable, and lets a shared type resolve to one class instead of
many blank-node copies. The cost is more classes in the vocabulary; the benefit is
that the RDF graph reflects 3GPP's actual type reuse. This is a modelling opinion,
not a standard requirement.

---

## 5. Class identity comes from the YANG *grouping*, not the list node

The most opinionated choice. A YANG list node is usually named after the
*collection* (`serviceProfileList`), but its content comes from a `grouping`
(`ServiceProfileGrp`). We name and identify the class from the **grouping**
(`ServiceProfile`), so:

- entry classes are named after the *element type*, not the collection;
- multiple list nodes that `use` the same grouping resolve to **one shared class**.

The class namespace is the grouping's **home module** (resolved through submodule
`belongs-to`). Fallback to node-based naming when there isn't exactly one
non-base grouping. Base structural groupings (`Top_Grp`, `ManagedFunctionGrp`,
etc.) are excluded from this naming so they don't hijack it.

Why flag it: this means the RDF class name may **not** textually match any single
YANG node name — it matches the grouping. An expert diffing YANG against RDF
should expect `ServiceProfileGrp → ex:ServiceProfile`, referenced by a
`serviceProfileList` property. This is intentional and, we argue, more faithful to
the *semantics* (one type, reused) than mirroring collection names.

---

## 6. Known limitations / honest gaps

- **`choice`/`case` mutual-exclusivity is not expressed.** Case leaves are
  flattened onto the owning class so **no data is lost**, but the "exactly one
  case" constraint is **not** emitted (no `sh:xone`). A consumer will see all case
  leaves as optional siblings. Adding `sh:xone` is a candidate improvement.
- **Names live in IRIs + `rdfs:comment` only** — no `rdfs:label`/`skos:prefLabel`
  is emitted. Human-readable labels would help generic RDF tools; currently the
  local name is carried by the IRI and the YANG `description` by `rdfs:comment`.
- **Reference-layer predicates are undeclared** (see §1 audit note).
- **DN range inference is name-heuristic** and deliberately fenced into
  `*_refs.ttl`; ~unresolved references are listed, never silently ranged.
- **`identityref` → `rdfs:subClassOf` is not implemented** (3GPP NRM defines very
  few identities; deferred as low-value).

---

## 7. What a reviewer can rely on

- Load the base `*_rdf.ttl` + `*_shacl.ttl` and you get standards-only RDF/OWL/SHACL
  **plus** the five declared `nrm:` terms — nothing else non-standard.
- Skip `*_refs.ttl` (`--no-inference`) and there is **zero heuristic content** in
  the output.
- IRIs are derived deterministically from YANG namespaces and names; the same input
  produces byte-identical output.
- Every deviation above is a modelling choice made to be *more* faithful to 3GPP
  semantics, not a shortcut — and each is isolated (own vocabulary term, own file,
  or clearly documented) so it can be reviewed, kept, or replaced independently.
