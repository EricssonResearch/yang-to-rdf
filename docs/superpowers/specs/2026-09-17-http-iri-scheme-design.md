# Design: HTTP IRI scheme + containerised reproducibility

_Status: approved design, not yet implemented. Date: 2026-09-17._

## 1. Problem

Emitted term IRIs are URNs taken from each module's YANG `namespace` statement,
with the class and property names appended as path segments:

```
urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction
urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction/pLMNId
```

Three problems with this, in order of how much they matter:

1. **URNs do not dereference**, and the repo is being published. A published
   vocabulary should use `http(s)` IRIs so a client can, in principle, retrieve a
   description of a term.
2. **The local name of a property is not an NCName.** Relative to the module
   namespace, `AMFFunction/pLMNId` contains `/`. See §3 — this is the constraint
   that shapes the whole design.
3. **Three IRIs are minted under `https://3gpp.org/`** (`nrm/vocab#`,
   `nrm/ontology`, `nrm/ontology/version/<label>`) — a domain this project does
   not control, for terms this project invented. Publishing that asserts an
   authority we do not have.

Scope of this design: the IRI scheme, the configuration surface that controls it,
the correctness gates that hold it in place, and a containerised verification path
that a third party can run. Out of scope: §11.

## 2. Decisions

| # | Decision |
|---|---|
| D1 | Term IRIs are `https` IRIs under a configurable base, default `https://semantics.ericsson.com/`. |
| D2 | Module identity is the **declared module name**, not the YANG namespace and not the filename. |
| D3 | Each module gets a **hash namespace** (one vocabulary document per module). |
| D4 | Properties are **class-scoped** within the module namespace, joined with `.`. |
| D5 | SHACL NodeShapes live in a **separate document namespace** from classes. |
| D6 | The discarded YANG namespace URN is **retained as provenance** on each module ontology. |
| D7 | The minted vocabulary moves to `<base>vocab#` and its prefix is renamed `nrm:` → `y2r:`. |

### References these decisions rest on, and their standing

Stating status matters: only one of these is a Recommendation, and the two that
speak most directly to vocabulary publishing are the weakest.

| Reference | Status | Used for |
|---|---|---|
| [XML Namespaces 1.0 3e](https://www.w3.org/TR/xml-names/) | **W3C Recommendation**, 8 Dec 2009 | The `NCName` production. `NCName ::= Name - (Char* ':' Char*)`, so `/` is excluded by construction and the first character must be a letter or `_`. |
| [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986) | **IETF Standard** (STD 66) | Generic URI syntax; the `fragment` and `segment` productions; `-._~` are unreserved. |
| [RFC 7950](https://www.rfc-editor.org/rfc/rfc7950) | **IETF Proposed Standard** | YANG `identifier` grammar (§6.2), module-name and namespace uniqueness, `belongs-to` submodule resolution. |
| [Best Practice Recipes for Publishing RDF Vocabularies](https://www.w3.org/TR/swbp-vocab-pub/) | W3C **Working Group Note**, 28 Aug 2008 — states it is "inappropriate to cite this document as other than work in progress" | Hash-vs-slash guidance and the "local name must be a legal NCName" requirement. Guidance, not a requirement. |
| [Cool URIs for the Semantic Web](https://www.w3.org/TR/cooluris/) | W3C **Interest Group Note**, 3 Dec 2008 | Background on 303 vs hash dereferencing. Guidance only. |

## 3. Why hash namespaces (D3, D4)

The Recipes note says both hash and slash namespaces are acceptable and tells you
to choose on **size, rate of addition, and how users access individual terms**,
with hash suited to a vocabulary "served in a single Web access". Measured over
the committed examples (§12):

```
modules with terms      107        median terms/module    70
distinct terms        8,171        max terms/module      256
                                   modules over 500        0
largest _rdf.ttl     107 KiB       median               23 KiB
```

(Terms-per-module counts the distinct term IRIs *appearing in* that module's
`_rdf.ttl`, which is the right measure for "can this be one Web access" — it
includes cross-module references, so the per-module figures do not sum to the
corpus-wide distinct count. The file sizes corroborate the same conclusion by an
independent path.)

That is the note's small-vocabulary case. The practical consequence is what
decides it: a hash namespace needs only **Recipe 1** — serve one static file per
module. No 303 redirects, no content negotiation, no server rewrite rules. Since
`semantics.ericsson.com` does not exist yet (§7), whoever eventually stands it up
should not have to configure Apache to make the IRIs resolve.

A hash namespace also fixes problem 2 from §1. With `<base>yang/<module>#` as the
namespace, every local name is a legal NCName and **all of a module's terms share
one namespace** — so a prefix binds them and tools that assume one vocabulary per
document can group them. Under the old two-level slash form, properties sat in a
namespace per class: 535 namespaces instead of 118, with nothing binding them.

### Properties must be class-scoped

Flattening properties to `#pLMNId` was considered and rejected on measurement:

```
(module, property) pairs                        4,523
  reused across >1 class within one module        655   (14.5%)
property 'id' appears on                          178   distinct classes
```

A flat per-module namespace would silently merge those 655 into shared IRIs. So
the class scope is required, and it must live inside the fragment.

### The separator is `.`, and it is ours

`.` is a legal non-initial NCName character. It is chosen over `-` on
measurement: of 1,482 distinct local names, **0 contain `.` and 4 contain `-`**.

**No unambiguous ASCII separator exists.** RFC 7950 identifiers permit letters,
digits, `_`, `-`, and `.`; NCName permits the same set. Every candidate separator
is therefore also legal inside a YANG identifier, so `#A.B` is in principle
ambiguous between property `B` of class `A` and a class named `A.B`. This is
handled by **refusing** rather than by hoping: gate G9 (§8) rejects any class or
property identifier containing `.`, with an error naming the reason. On the
Rel-19 set that guard cannot fire, so it is tested with a fixture that does
contain a dot.

This separator convention is **minted by this project**. It asserts no external
authority and is not drawn from any standard. It is recorded here, at the code
that implements it, and in the error message that enforces it.

## 4. The scheme

```
<base> = https://semantics.ericsson.com/          (--base-iri; absolute http(s))

<base>vocab#<term>                    minted vocabulary            prefix y2r:
<base>ontology                        aggregate ontology        →  index.ttl
<base>ontology/version/<label>        owl:versionIRI

<base>yang/<module>                   per-module vocabulary URI →  <module>_rdf.ttl
<base>yang/<module>#<Class>           class (IOC or dataType) and typedef
<base>yang/<module>#<Class>.<prop>    property, class-scoped

<base>shapes/<module>                 shapes document URI       →  <module>_shacl.ttl
<base>shapes/<module>#<Class>         SHACL NodeShape
```

Worked example:

```turtle
@prefix y2r:     <https://semantics.ericsson.com/vocab#> .
@prefix amf3gpp: <https://semantics.ericsson.com/yang/_3gpp-5gc-nrm-amffunction#> .

<https://semantics.ericsson.com/yang/_3gpp-5gc-nrm-amffunction>
    a owl:Ontology ;
    y2r:yangModuleName "_3gpp-5gc-nrm-amffunction" ;
    y2r:yangNamespace  <urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction> ;
    owl:versionInfo    "revision 2026-05-25 (CR-1702)" .

amf3gpp:AMFFunction a rdfs:Class ; rdfs:subClassOf y2r:ManagedFunction .
amf3gpp:AMFFunction.pLMNId rdfs:domain amf3gpp:AMFFunction .
```

The three output layers map one-to-one onto three namespaces, which is why D5
costs nothing: `_rdf.ttl` ↔ `<base>yang/<module>#`, `_shacl.ttl` ↔
`<base>shapes/<module>#`, and `_refs.ttl` only adds triples *about* terms in the
first, so it needs no namespace of its own.

D5 also removes a latent collision structurally: with shapes in the class
namespace, a YANG class genuinely named `FooShape` would collide with the shape of
`Foo`. Measured 0 occurrences on this corpus — which is exactly why it must be
designed out rather than left to the corpus.

### Turtle prefixes

Bound from each module's **own YANG `prefix` statement** (`amf3gpp`, `mf3gpp`, …)
rather than invented. Measured: 118 modules, 118 distinct prefixes, all
NCName-legal, 0 collisions. YANG only requires prefix uniqueness within a module's
import scope, not across a set, so a deterministic fallback (append `-2`, `-3`, …
in sorted module order) is required for arbitrary input.

### Module identity (D2)

The declared module name from pyang's parse tree — not the filename (robust to
`<name>@<revision>.yang`) and not the namespace. Submodules resolve to their
parent module via `belongs-to`; there are 2 in this set.

Keying on the module name rather than the namespace also corrects two real
upstream discrepancies, in the IRIs **and** in the output filenames, which are
currently derived from the URN tail:

| Module | YANG namespace | Currently emitted as | Becomes |
|---|---|---|---|
| `_3gpp-5gc-nrm-externalseppfunction` | `urn:3gpp:sa5:_3gpp-5gc-nrm-ex**tt**ernalseppfunction` | `…extternalseppfunction` (upstream typo) | `…externalseppfunction` |
| `_3gpp-nr-nrm-nrsectorcarrier` | `urn:3gpp:sa5:_3gpp-nr-nrm-nrnetwork-nrsectorcarrier` | `…nrnetwork-nrsectorcarrier` | `…nrsectorcarrier` |

Nothing is lost: D6 keeps the exact namespace as `y2r:yangNamespace`, so the
mapping stays queryable and reversible, including for these two.

## 5. Configuration surface

`--base-iri BASE`, default `https://semantics.ericsson.com/`. Validated: must
parse under RFC 3986 as absolute with scheme `http`/`https` and a non-empty
authority; a missing trailing `/` is normalised in. Rejection names the
constraint.

The default is the proposed scheme, not a legacy fallback — there is no flag that
restores URN IRIs.

**Pre-existing doc defect to fix in the same change.** `--base-namespace` is
documented as if it exists — `CHANGELOG.md:35` and `VERSIONING.md:146,149,150,165`,
the last being a whole "when you DO want distinct per-release IRIs" recipe — but
no such flag is in the CLI (verified against `yang-to-rdf --help`). All five
references are corrected to `--base-iri`.

## 6. Code changes

The refactor is contained because `output_writer.split_graph()` already partitions
by prefix-matching whatever namespaces the parser reports, and its docstring
already anticipates this: *"scheme-agnostic, so non-3GPP or non-URN namespaces
split correctly too."* The parser changes what it reports; the machinery follows.

| File | Change |
|---|---|
| `namespace.py` | Base derived from `--base-iri`. `module_iri`, `class_iri`, `property_iri`, new `shape_iri`. NCName validation; `.`-separator rejection; identifier validation naming RFC 7950 §6.2. `y2r:` replaces `NRM`. |
| `yang_parser.py` | `Klass.namespace` / `Typedef.namespace` carry the module's hash namespace instead of the URN. New `Model.module_yang_namespace` for D6. Submodule → parent module name. `MANAGED_FUNCTION_IRI` derived from the base. |
| `output_writer.py` | `module_ns()` matches `s == ns` or `s.startswith(ns + "#")` (was `"/"`), over a `{prefix → module}` map so classes and shapes both route. `module_stem()` from the module name. `INDEX_ONTOLOGY` and the version IRI from the base. Emit D6 provenance triples. Bind YANG-derived prefixes. |
| `shacl_converter.py` | Shapes use `shape_iri` in the shapes namespace. |
| `reference_layer.py` | Follows the new `property_iri`. |
| `main.py` | `--base-iri`; thread the base into `parse()` and the converters. |
| `scripts/iri_census.py` | **New.** The committed implementation of gates G1–G9 and the source of every number in §12 — so the figures are reproducible and the gate and the measurement cannot drift apart. |
| `scripts/verify.py` | **New.** The container entry point (§9). |
| `Dockerfile` | **New** (§9). |
| `CONVERSION_NOTES.md` | §1 rewritten for `y2r:` at `<base>vocab#`; new subsection on the scheme, the `.` convention as ours, and the non-dereferenceable default. §2's `module` row updated. |
| `VERSIONING.md` | Rewritten for the new IRIs; `--base-namespace` → `--base-iri`; the "stable per RFC 7950" claim re-grounded on module-name stability. |
| `README.md` | IRI Strategy section; internal Pages link removed. |
| `CHANGELOG.md` | 0.3.0 entry. |

## 7. The default base does not resolve

`semantics.ericsson.com` has no DNS record (checked 2026-09-17; `ericsson.com`
resolves, the subdomain does not). This is stated plainly rather than left for a
reader to discover: the namespace is Ericsson-owned, **not currently
dereferenceable**, minted by this project, and asserts no 3GPP endorsement. That
statement goes in `CONVERSION_NOTES.md`, in a comment at the constant, and in the
`--base-iri` help text.

The scheme is chosen so that serving it later requires only static files (§3).

## 8. Correctness gates

Each runs over the **full converted Rel-19 output** unless marked fixture-only,
and each has a stated expectation. Implemented in `scripts/iri_census.py`, invoked
by the test suite and by the container.

| Gate | Asserts | Expectation | Can real data reach it? |
|---|---|---|---|
| G1 | every emitted IRI is absolute, scheme ∈ {http, https}, non-empty authority, RFC 3986-legal per component | 100% of 8,278 | yes |
| G2 | `(module, class[, prop]) → IRI` is injective, over the `.`-joined form | N inputs → N distinct IRIs, both counts printed | yes |
| G3 | no `urn:` IRI survives except D6 provenance objects | **exactly 118**, counted | yes |
| G4 | rdflib serialize → parse → compare over the real output | set equality, per layer | yes |
| G5 | an identifier that is not a valid YANG identifier is refused, naming RFC 7950 §6.2 | raises | **fixture only** |
| G6 | a class named `FooShape` does not collide with the shape of `Foo` | distinct IRIs | **fixture only** — 0 on this corpus |
| G7 | declared module name == filename stem | 120/120; divergence warns, does not fail | yes |
| G8 | every local name is a legal NCName, by a regex derived from the XML Names Recommendation | 100% of 8,171 | yes |
| G9 | no class or property identifier contains `.` | 0 of 1,482; raises if violated | **fixture only** — 0 on this corpus |

Two rules applied to these gates, both learned the hard way:

- **Each gate is inverted and watched to fail before it is trusted** — delete the
  guarded line, corrupt the input, flip the separator — then restored. G2, G3, G6
  and G9 especially, since a gate that never fires produces no number at all.
- **G5, G6 and G9 cannot be exercised by real 3GPP YANG.** Their test docstrings
  say so, so a green suite is not read as coverage it does not have. Where a gate
  enumerates what it inspects, it asserts the count inspected, so a path that goes
  stale after a rename fails loudly instead of quietly scanning less.

## 9. Containerised verification

The container **is** the install documentation: the `Dockerfile` runs exactly the
commands in the README's Install section, from `python:3.12-slim`. The single
substitution is `git clone` → `COPY` (so it works before publication), documented
inline as the only difference. A test extracts the shell commands from the README
Install section and asserts each appears verbatim in the `Dockerfile`, and asserts
the extracted count is non-zero — so a renamed heading fails rather than silently
scanning nothing.

```bash
docker build -t yang-to-rdf .
docker run --rm yang-to-rdf            # full verification
docker run --rm yang-to-rdf --offline  # stages 0-3 only, explicitly
```

One committed entry point, `scripts/verify.py`, invoked with `uv run`:

| # | Stage | Checks |
|---|---|---|
| 0 | provenance | git HEAD + dirty flag, tool / rdflib / pyang versions, forge commit sha, timestamp |
| 1 | `uv sync --locked` | the lockfile installs on a clean base |
| 2 | `uv run pytest -q` | unit tests |
| 3 | `uv build`, install the wheel in a fresh venv, `yang-to-rdf --version` | packaging metadata; the path a package user takes |
| 4 | convert `--fetch-release Tag_Rel19_SA112 --ref-type tags` | real conversion from an immutable input |
| 5 | `scripts/iri_census.py` over the output | gates G1–G4, G7, G8 |
| 6 | diff output against committed `examples/` | **zero differing files** |
| 7 | summary | asserts stage count == 8, so a new stage cannot appear unsummarised |

Without network, stages 4–6 **fail** with a stated reason. They skip only under
an explicit `--offline`, which also suppresses the summary's success claim. A
harness that quietly runs three of seven stages and prints a summary is worse than
one that fails.

Every run writes a stamped `verification-report.json`: stage results, the
measured numbers, and the provenance from stage 0. Numbers presented from a dirty
tree are marked as such.

## 10. Examples, pinned

`examples/` is regenerated from forge tag **`Tag_Rel19_SA112`** (commit
`24ffa42e`), with tag and sha recorded in the examples README and in the
aggregate ontology metadata. Today's snapshot came from a local zip of the moving
`Rel-19` branch and cannot be re-derived by anyone.

The diff against the current snapshot is **reported before it is committed** — the
extent of upstream movement between the July branch state and the tag is not yet
measured, and will not be guessed.

## 11. Out of scope

- **Ontology documentation / pyLODE.** Deferred by explicit decision: the current
  HTML output navigates badly. One plausible mechanism is that properties sat in
  a namespace per class, so nothing bound them — which §3 changes. That is a
  hypothesis, not a diagnosis; it has not been verified and this design does not
  claim to fix it. Re-evaluate after implementation.
- **GitHub Pages.** Not wired. The README loses its internal docs link rather than
  gaining a link to output known to be poor.
- **A `w3id.org` PURL.** The scheme is compatible with being fronted by one later;
  obtaining one is an external process and is not attempted here.
- **Actually serving `semantics.ericsson.com`.** Out of this repo's control.
- **Remodelling.** The `choice`/`sh:xone` gap, missing `rdfs:label`s, undeclared
  reference-layer predicates, and `identityref` remain as recorded in
  `CONVERSION_NOTES.md` §6. This design changes identifiers, not the model.

## 12. Measurements this design rests on

Every figure above comes from the committed `scripts/iri_census.py` once it
exists. Measured 2026-09-17 against `examples/` at `a795ec7` and the 120 `.yang`
files of `MnS-Rel-19-yang-models.zip`:

| Figure | Value |
|---|---|
| YANG files / modules / submodules | 120 / 118 / 2 |
| distinct YANG namespaces | 118 (115 `urn:3gpp:sa5`, 3 `urn:ietf:params`) |
| namespace collisions | 0 |
| modules where namespace tail ≠ module name | 2 |
| filename stem ≠ declared module name | 0 of 120 |
| module names, character set | `[-0-9A-Za-z_]` only |
| YANG prefixes: count / distinct / NCName-legal | 118 / 118 / all |
| distinct URN IRIs in examples | **8,278** = 107 module ontologies + 1,084 classes/typedefs + 946 shapes + 6,141 properties (partitions exactly) |
| of those, **terms** taking a hash local name | **8,171** — 7,225 in `yang/`, 946 in `shapes/` |
| 1,084 classes/typedefs vs 946 shapes | the 138 difference is typedefs (`rdfs:Datatype`), which correctly get no NodeShape — not a parity violation |
| distinct local-name segments | 2,014, all alphanumeric, 0 needing percent-encoding |
| terms per module (distinct IRIs appearing in one `_rdf.ttl`; counts cross-module references, so does not sum to 8,171) | median 70, max 256, 0 modules over 500 |
| largest / median `_rdf.ttl` | 107 KiB / 23 KiB |
| (module, property) pairs | 4,523 |
| properties reused across classes in one module | 655 (14.5%) |
| classes bearing property `id` | 178 |
| local names containing `.` / `-` | 0 / 4 of 1,482 |
| classes ending in `Shape`, and `X`/`XShape` collisions | 0 / 0 |
| rdflib 7.6.0 round-trip, 504 adversarial triples | identical in turtle, nt, xml, json-ld |

The rdflib probe covered identifiers with embedded dots, a trailing dot, a leading
underscore, and `/`-containing property locals, and confirmed that binding a
per-module prefix does not cause rdflib to emit an illegal prefixed name.
