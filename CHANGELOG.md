# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
as much as possible for a pre-1.0 project.

## [0.3.0]

### Changed

- **BREAKING: term IRIs are now HTTP IRIs in a per-module hash namespace.**
  Previously each module's YANG `namespace` URN was the base, with the class and
  property appended as path segments:

  ```
  urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction/pLMNId      (before)
  https://semantics.ericsson.com/yang/_3gpp-5gc-nrm-amffunction#AMFFunction.pLMNId
  ```

  The mapping rule: `<base>yang/<declared module name>#<Class>[.<prop>]`, with
  SHACL shapes under `<base>shapes/<module>#<Class>`. `<base>` defaults to
  `https://semantics.ericsson.com/` and is set with the new `--base-iri`.

  Rationale, in short: a URN does not dereference, and the old property local name
  contained a `/`, so it was not a legal `NCName` — the one hard requirement in
  this area, from the XML Namespaces Recommendation. A hash namespace per module
  also gives each module one namespace, so a prefix binds all its terms. See
  CONVERSION_NOTES.md §1a for what the scheme rests on and the standing of each
  reference.
- **Module identity is keyed on the declared module name**, not the YANG
  `namespace`. This corrects two upstream discrepancies in the 3GPP Rel-19 set —
  an `extternalseppfunction` typo and a `nrnetwork-nrsectorcarrier` mismatch — in
  both the IRIs and the output filenames. The original URN is retained as
  `y2r:yangNamespace` on each module ontology, so the mapping stays queryable.
- **The minted vocabulary prefix `y2r:` is now `y2r:`**, namespaced under
  `<base>vocab#` instead of `https://3gpp.org/nrm/vocab#` — a domain this project
  does not control, for terms this project invented.
- Turtle output binds each module's own YANG `prefix`, so it reads
  `amf3gpp:AMFFunction.aMFSetRef` rather than a full IRI.
- `examples/` is regenerated from the immutable forge tag `Tag_Rel19_SA112`
  (commit `24ffa42e`) and now reproduces byte-for-byte. The previous snapshot came
  from the moving `Rel-19` branch tip and could not be re-derived.
- CI moved from GitLab to GitHub Actions, which now also builds and runs the
  verification container.

### Added

- **`--base-iri`** to relocate every emitted term under a different authority.
- **`scripts/iri_census.py`** — six gates over real output (absolute-http validity,
  injectivity, no URN leakage, rdflib round-trip, filename/module agreement,
  NCName legality). Each reports the size of the candidate set it searched. This
  script is the single definition of the IRI figures quoted in the documentation.
- **`Dockerfile` + `scripts/verify.py`** — one entry point running install, tests,
  a wheel build installed into a fresh virtualenv, conversion of the pinned tag,
  the gates, and a byte-for-byte diff against `examples/`. The Dockerfile runs the
  README's install commands verbatim and a test asserts that correspondence.
  Without network the dependent stages fail rather than skip.

### Fixed

- `--base-namespace` was documented in `CHANGELOG.md` and four places in
  `VERSIONING.md`, including a worked recipe, but **never existed**. The
  capability now exists as `--base-iri` and the stale references are corrected.
- `stamp_versions` iterated only modules carrying a `revision` statement, so any
  module without one silently received no ontology declaration, no Dublin Core
  metadata and no provenance.
- `pyproject.toml` said version `0.2.0` while `--version` reported `0.3.0`; the two
  are now guarded by a test.
- A stale docstring in `rdf_converter._assign_labels` gave the qualified label form
  as `amffunction:PerfMetricJob`; real output uses the full module name.
- The claim that IRIs are release-stable is now cited to RFC 7950 §11 rather than
  to the specification in general, and its limits are stated: module names are
  unique per server, not globally.

## [0.2.0]

### Added

- **Per-module split output (default).** Each layer is written as one file per
  source YANG module (`<module>_rdf.ttl`, `_shacl.ttl`, `_refs.ttl`) plus an
  `index.ttl` that carries the `y2r:` vocabulary and `owl:imports` every module.
  Pass `--single-file` for the previous merged one-file-per-layer output.
- **Auditable reference-inference layer (`_refs.ttl`).** DistinguishedName
  references are marked `y2r:isReference` with an open range in the base TBox;
  inferred `rdfs:range` targets live separately with `y2r:confidence`
  (`unambiguous`/`unresolved`) and `y2r:inferredBy` provenance.
- **3GPP `<<dataType>>` structured attributes** modeled as their own
  `rdfs:Class`, linked from the owning class by an `owl:ObjectProperty` and
  `y2r:hasAttribute`. dataType/IOC classes are named and shared by their YANG
  grouping, so a grouping reused across many list nodes yields one shared class
  (e.g. `ServiceProfile`, `GeoArea`).
- Test suite (previously none), run against a complete 3GPP module set.

### Changed

- **Parser rebuilt on pyang's *resolved* schema tree** (`i_children`,
  `augment.i_target_node`, resolved typedef chains) instead of string heuristics
  over the raw statement tree. Containment, inheritance, and type resolution are
  now derived from real YANG resolution.
- IRIs are derived from each module's own YANG `namespace` (URN), not a
  hard-coded HTTP base. (Superseded in 0.3.0 by HTTP IRIs and `--base-iri`.)
- Typedefs emit `rdfs:Datatype` (previously `rdfs:Class`).

### Fixed

- Validation errors are now surfaced instead of silently swallowed; a complete
  module set (with its `external-yams/` dependencies) is required.
- `choice`/`case` and nested-`container` attribute leaves are flattened onto the
  owning class rather than dropped.

## [0.1.0]

- Initial converter: YANG → RDF/SHACL using string-heuristic parsing of the raw
  pyang statement tree.
