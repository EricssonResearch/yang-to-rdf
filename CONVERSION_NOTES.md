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
- **One small project vocabulary, `y2r:`**, carries the handful of 3GPP-specific
  relationships that have no direct standard equivalent. It is namespaced under
  `https://semantics.ericsson.com/vocab#` and is the *entire* non-standard term
  surface. Every term is listed below with its justification.
- **The IRI scheme itself is a proposal, not a standard.** §1a states what it
  rests on, which parts are ours, and what the default namespace does and does
  not claim.
- **No reasoner-dependent semantics are asserted** (no `owl:inverseOf`,
  `owl:disjointWith`, domain/range as OWL restrictions used for inference). RDFS
  `domain`/`range` are used descriptively, and constraints are pushed into SHACL,
  which is closed-world and validation-oriented — the right fit for schema data.

---

## 1. The `y2r:` vocabulary — the complete non-standard surface

Base: `https://semantics.ericsson.com/vocab#` (relocatable with `--base-iri`).
These are the only terms the tool mints outside standard vocabularies.

| Term | Declared as | Purpose | Why not a standard term |
|---|---|---|---|
| `y2r:ManagedFunction` | `rdfs:Class` | Common superclass for network-function IOCs (those whose YANG grouping `uses ManagedFunctionGrp`). | 3GPP domain concept; no standard class means "managed function". |
| `y2r:nameContains` | `owl:ObjectProperty` | 3GPP **name-containment** hierarchy — the parent→child structure a DN path encodes (e.g. `SubNetwork` contains `ManagedElement` contains `AMFFunction`). Emitted from YANG `augment`/nested-list structure. | This is 3GPP's specific containment relation, distinct from `rdfs:subClassOf` (that's inheritance) and from generic part-of vocabularies; naming it explicitly keeps it unambiguous. |
| `y2r:hasAttribute` | `owl:ObjectProperty` | Links an IOC (or dataType) to a **structured `<<dataType>>` attribute class** built from a nested `list` inside an `attributes` container. | Distinguishes "a structured attribute value" from `y2r:nameContains` (a contained managed object) — a real 3GPP modelling distinction that no standard predicate captures. |
| `y2r:isReference` | `owl:ObjectProperty`* | Marks a property whose YANG type is a `DistinguishedName` (a reference to another object) rather than a literal value. | See §3 — DN references have no schema-declared target, so we flag them rather than fabricate a `rdfs:range`. |
| `y2r:isInvariant` | `owl:DatatypeProperty`* | Marks a property carrying the 3GPP `yext3gpp:inVariant` extension (set-once / immutable after creation). | 3GPP YANG extension with no OWL/SHACL equivalent; preserved as an annotation so the semantics aren't lost. |

\* `y2r:isReference` and `y2r:isInvariant` are used as **annotation flags** on
properties (object of `true`), not as relationships between individuals. They are
declared with an `owl:` property type for tooling convenience; treat them as
boolean markers, not as assertions requiring OWL reasoning.

### Provenance predicates (on each module ontology)

| Term | Value | Meaning |
|---|---|---|
| `y2r:yangModuleName` | string | The declared YANG module name the IRI was keyed on. |
| `y2r:yangNamespace` | IRI | The module's YANG `namespace` statement, retained verbatim. |

Module identity is keyed on the **declared module name**, so the YANG `namespace`
would otherwise be discarded. It is kept because it is the only record of the
original URN — and in the 3GPP Rel-19 set two namespaces disagree with their
module name, so the mapping is not derivable after the fact:

| Module | Its YANG namespace |
|---|---|
| `_3gpp-5gc-nrm-externalseppfunction` | `urn:3gpp:sa5:_3gpp-5gc-nrm-ex**tt**ernalseppfunction` (upstream typo) |
| `_3gpp-nr-nrm-nrsectorcarrier` | `urn:3gpp:sa5:_3gpp-nr-nrm-nrnetwork-nrsectorcarrier` |

### Reference-layer predicates (in `*_refs.ttl` only)

These appear **only** in the separate, opt-out reference-inference layer and are
provenance for a heuristic (see §3):

| Term | Value | Meaning |
|---|---|---|
| `y2r:confidence` | `"unambiguous"` / `"unresolved"` | Whether the inferred range is trusted. |
| `y2r:inferredBy` | `"dn-name-suffix"` | Which heuristic produced the guess. |
| `y2r:candidate` | string | The guessed target class name when unresolved. |

> **Known gap (audit note):** these three reference-layer predicates are currently
> *used* but **not formally declared** (no `rdf:type`/`rdfs:comment` triple) in the
> emitted vocabulary, unlike the five core `y2r:` terms which are declared in the
> base RDF layer. They are provenance annotations, so this is low-impact, but a
> strict OWL consumer will see undeclared predicates. Declaring them is a
> reasonable future improvement.

---

## 1a. The IRI scheme — what it rests on, and what is ours

```
<base> = https://semantics.ericsson.com/          (--base-iri)

<base>vocab#<term>                    minted vocabulary            prefix y2r:
<base>ontology                        aggregate ontology        →  index.ttl
<base>ontology/version/<label>        owl:versionIRI
<base>yang/<module>                   per-module ontology       →  <m>_rdf.ttl
<base>yang/<module>#<Class>           class (IOC / dataType) and typedef
<base>yang/<module>#<Class>.<prop>    property, class-scoped
<base>shapes/<module>#<Class>         SHACL NodeShape           →  <m>_shacl.ttl
```

Each module binds its own YANG `prefix` statement, so the Turtle reads like the
source: `amf3gpp:AMFFunction.aMFSetRef`.

### What this rests on, and how much weight each carries

Stating the status matters, because only one of these is a Recommendation and the
two that speak most directly to vocabulary publishing are the weakest:

| Reference | Status | Used for |
|---|---|---|
| [XML Namespaces 1.0 3e](https://www.w3.org/TR/xml-names/) | **W3C Recommendation**, 8 Dec 2009 | The `NCName` production. `/` is excluded by construction; the first character must be a letter or `_`. |
| [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986) | **IETF Standard** (STD 66) | URI syntax; `-._~` are unreserved. |
| [RFC 7950](https://www.rfc-editor.org/rfc/rfc7950) | IETF **Proposed Standard** | YANG `identifier` grammar (§6.2), module/namespace uniqueness, `belongs-to`. |
| [Best Practice Recipes for Publishing RDF Vocabularies](https://www.w3.org/TR/swbp-vocab-pub/) | W3C **Working Group Note**, 28 Aug 2008 — says of itself that it is "inappropriate to cite this document as other than work in progress" | Hash-vs-slash guidance, and the "local name must be a legal NCName" requirement. Guidance, not a requirement. |
| [Cool URIs for the Semantic Web](https://www.w3.org/TR/cooluris/) | W3C **Interest Group Note**, 3 Dec 2008 | Background on 303 vs hash dereferencing. |

**Why a hash namespace per module.** The Recipes note says to choose on size, and
a module here has a median of 70 terms, at most 256, in a file of at most 136 KB —
its "served in a single Web access" case. The consequence that decides it: a hash
namespace needs only the note's Recipe 1, so serving these IRIs later requires
static files and no server configuration — no 303 redirects, no content
negotiation. It also gives every module ONE namespace, so a prefix binds all its
terms; the previous two-level slash form put properties in a namespace per class.

### Ours, and asserting nothing

- **`semantics.ericsson.com` is an Ericsson-owned namespace minted by this
  project. It is not currently dereferenceable** (no DNS record as of
  2026-09-17) and asserts no 3GPP endorsement. `--base-iri` relocates every term.
- **The `.` joining a class and property local name is our convention.** No
  standard prescribes it. It was already this project's `rdfs:label` convention,
  so the IRI local name and the label now coincide.
- Class scoping is not decorative: 655 of 4,523 `(module, property)` pairs reuse a
  property name across classes within one module (`id` alone spans 178 classes), so
  a flat namespace would silently merge distinct properties into one IRI.
- **No ASCII separator is free of a theoretical ambiguity**, because RFC 7950
  identifiers and NCNames permit the same character set: a class named `A.B` would
  collide with property `B` of class `A`. An earlier draft therefore refused every
  identifier containing `.` — which was wrong, because the IETF `ietf-yang-types`
  module that nearly every 3GPP module imports defines `typedef xpath1.0`
  (RFC 6991). The ambiguity is narrower than "contains a dot": a split is only a
  real alternative reading when *both* halves are legal YANG identifiers, and an
  identifier cannot begin with a digit, so `xpath1.0` has exactly one reading.
  `scripts/iri_census.py` gate G2 asserts this over the whole corpus; measured
  0 ambiguous of 10,234 terms.
- **SHACL shapes live in their own document namespace** (`<base>shapes/…#`) so a
  YANG class genuinely named `FooShape` cannot collide with the shape of `Foo`.
  There is no such class in the 3GPP set, which is exactly why the separation is
  structural rather than left to the corpus.

Every claim above is re-derivable:

```bash
uv run python -m scripts.iri_census examples/MnS-Rel-19-yang-models
```

## 2. YANG construct → RDF mapping (and the judgement calls)

| YANG construct | RDF output | Standard? | Note |
|---|---|---|---|
| `module` | `owl:Ontology` (per-module) + `owl:imports` in `index.ttl` | standard | IRI = `<base>yang/<declared module name>`; the YANG `namespace` is retained as `y2r:yangNamespace` (§1). |
| `list` with an `attributes` container (an IOC) | `rdfs:Class` | standard | "Is it an IOC?" is decided structurally (presence of `attributes`), not by name. |
| `list` inside `attributes` (a `<<dataType>>`) | `rdfs:Class` + `y2r:hasAttribute` link | **deviation** | 3GPP structured attributes become first-class classes rather than blank nodes — see §4. |
| `uses <X>Grp` (grouping) | class **named/identified by the grouping** | **deviation** | See §5 — this is the most opinionated choice. |
| `uses ManagedFunctionGrp` | `rdfs:subClassOf y2r:ManagedFunction` | standard use, project class | Inheritance. |
| `augment` / nested sub-IOC list | `y2r:nameContains` | project predicate | Containment (§1). |
| `leaf` | `rdf:Property` + `rdfs:domain` + `rdfs:range` (XSD) | standard | Range from the resolved type chain. |
| `leaf` typed `DistinguishedName`/`Dn`/`LDN` | `owl:ObjectProperty` + `y2r:isReference`, **no `rdfs:range`** | **deviation** | §3. |
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
  `y2r:isReference` and, crucially, emit **no `rdfs:range`** in the base ontology —
  asserting a range we cannot justify would be fabrication.
- **Range *inference* is a separate, opt-out layer** (`*_refs.ttl`). It guesses the
  target by stripping a `Ref`/`RefList`/… suffix from the leaf name and matching
  against class names, tagged with `y2r:confidence`. This is explicitly a
  heuristic, physically separated from the base TBox, and labelled as such so a
  consumer can ignore it or audit every guess.

This separation is the deliberate design: **the base ontology contains only what
the schema states; anything inferred is quarantined and provenance-tagged.**

---

## 4. Structured attributes as classes (not blank nodes)

3GPP `<<dataType>>` attributes (a nested `list` inside `attributes`) could be
modelled as anonymous/blank-node structures. We instead mint a **named
`rdfs:Class`** and link it with `y2r:hasAttribute`.

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
  **plus** the five declared `y2r:` terms — nothing else non-standard.
- Skip `*_refs.ttl` (`--no-inference`) and there is **zero heuristic content** in
  the output.
- IRIs are derived deterministically from the declared module name and term names;
  the same input produces byte-identical output, which
  `examples/MnS-Rel-19-yang-models/` is pinned to demonstrate.
- Every deviation above is a modelling choice made to be *more* faithful to 3GPP
  semantics, not a shortcut — and each is isolated (own vocabulary term, own file,
  or clearly documented) so it can be reviewed, kept, or replaced independently.

---

## 8. Checking coverage ("do the YANG and the RDF represent the same things?")

A full round-trip (YANG → RDF → YANG, byte-identical) is **not** achievable here
by design — the conversion is the lossy projection described in §6. So equivalence
is checked as **coverage + parity**, not round-trip identity, by
`scripts/coverage_audit.py` (also enforced in `tests/test_coverage_audit.py`):

1. **Parser completeness** — the parser records any attribute node *kind* it did
   not model and surfaces it as an `unmodeled attribute node kind` warning. Zero
   warnings ⇒ no schema construct was silently skipped.
2. **RDF coverage** — every class, leaf, and structured-attribute link the parser
   produced appears as a triple in the RDF TBox.
3. **RDF/SHACL parity** — every emitted class has a SHACL NodeShape and vice
   versa (guards against the two converters drifting).

Run it against any module set:

```bash
python scripts/coverage_audit.py MnS-Rel-19-yang-models.zip   # exits non-zero on any gap
```

A **stronger** notion of equivalence — instance-level — is a separate, larger
exercise not yet automated here: validate the same RESTCONF/NETCONF sample against
the YANG (e.g. `yangson`/`yanglint`) and, converted to RDF, against the SHACL
(`pyshacl`); the schema and the shapes agree if they accept/reject the same
instances for the same reasons. This needs representative sample data and extra
dependencies.
