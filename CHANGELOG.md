# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
as much as possible for a pre-1.0 project.

## [0.2.0]

### Added

- **Per-module split output (default).** Each layer is written as one file per
  source YANG module (`<module>_rdf.ttl`, `_shacl.ttl`, `_refs.ttl`) plus an
  `index.ttl` that carries the `nrm:` vocabulary and `owl:imports` every module.
  Pass `--single-file` for the previous merged one-file-per-layer output.
- **Auditable reference-inference layer (`_refs.ttl`).** DistinguishedName
  references are marked `nrm:isReference` with an open range in the base TBox;
  inferred `rdfs:range` targets live separately with `nrm:confidence`
  (`unambiguous`/`unresolved`) and `nrm:inferredBy` provenance.
- **3GPP `<<dataType>>` structured attributes** modeled as their own
  `rdfs:Class`, linked from the owning class by an `owl:ObjectProperty` and
  `nrm:hasAttribute`. dataType/IOC classes are named and shared by their YANG
  grouping, so a grouping reused across many list nodes yields one shared class
  (e.g. `ServiceProfile`, `GeoArea`).
- Test suite (previously none), run against a complete 3GPP module set.

### Changed

- **Parser rebuilt on pyang's *resolved* schema tree** (`i_children`,
  `augment.i_target_node`, resolved typedef chains) instead of string heuristics
  over the raw statement tree. Containment, inheritance, and type resolution are
  now derived from real YANG resolution.
- IRIs are derived from each module's own YANG `namespace` (URN), not a
  hard-coded HTTP base. Use `--base-namespace` to override.
- Typedefs emit `rdfs:Datatype` (previously `rdfs:Class`).

### Fixed

- Validation errors are now surfaced instead of silently swallowed; a complete
  module set (with its `external-yams/` dependencies) is required.
- `choice`/`case` and nested-`container` attribute leaves are flattened onto the
  owning class rather than dropped.

## [0.1.0]

- Initial converter: YANG → RDF/SHACL using string-heuristic parsing of the raw
  pyang statement tree.
