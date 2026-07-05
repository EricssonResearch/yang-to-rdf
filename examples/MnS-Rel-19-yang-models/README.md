# Reference output — 3GPP MnS Rel-19 YANG models

Committed snapshot of the RDF/SHACL output produced by `yang-to-rdf` for the
complete 3GPP SA5 MnS Release 19 YANG module set. Kept in-repo as a reference
so consumers can inspect the vocabulary without running the tool, and so
changes to the ontology are reviewable as diffs.

## Files

Output is **split one file per source YANG module** (the default) so each file is
small and browsable directly on GitHub. For each module `<m>` there are up to
three files:

| File | Contents |
|---|---|
| `<m>_rdf.ttl` | RDFS/OWL ontology (TBox) for that module: IOC classes, 3GPP `<<dataType>>` classes, containment, inheritance, properties |
| `<m>_shacl.ttl` | SHACL NodeShapes for that module's classes |
| `<m>_refs.ttl` | Reference-inference layer for that module's DistinguishedName references (only if it has any) — inferred `rdfs:range` with `nrm:confidence` / `nrm:inferredBy` provenance |
| `index.ttl` | Aggregating ontology: the shared `nrm:` vocabulary + `owl:imports` of every module, plus `owl:versionIRI`/`owl:versionInfo` for the release. Load this to pull in the whole set. |

This snapshot was generated with `--release Rel-19`, so `index.ttl` carries
`owl:versionIRI <https://3gpp.org/nrm/ontology/version/Rel-19>` and each module
ontology carries an `owl:versionInfo "revision <date> (<CR>)"` from its YANG
`revision`. See [VERSIONING.md](../../VERSIONING.md) for loading multiple
releases side by side.

Cross-module links (e.g. `AMFFunction rdfs:subClassOf nrm:ManagedFunction`,
`ManagedElement nrm:nameContains AMFFunction`, or a property whose range is a
class defined in another module) live in the file of the triple's **subject**
module and resolve by IRI when the set is loaded together. A shared dataType
class (e.g. `ServiceProfile`, `GeoArea`) is defined once in its grouping's home
module and referenced by IRI elsewhere.

To produce a single merged file per layer instead, run with `--single-file`.

## Provenance

- Source: `MnS-Rel-19-yang-models.zip` (SHA-256 `7db850aaea7b6078bf62c6318e3cf9a7c3b9d987a7d49047a63ed51098e2de46`).
  Obtain 3GPP SA5 YANG from <https://forge.3gpp.org/rep/sa5/MnS>.
- Tool: `yang-to-rdf` v0.2.0.
- Command: `uv run yang-to-rdf MnS-Rel-19-yang-models.zip -o examples/MnS-Rel-19-yang-models`
- Generated: 2026-07-04.
- Layout: 105 modules → 284 per-module `.ttl` files + `index.ttl` (largest ~95 KB).
- Model summary: 501 IOCs, 445 dataType classes, 138 typedefs; reference layer
  121 unambiguous / 443 unresolved DN references. (dataType classes are named and
  shared by their YANG grouping, so a grouping reused across many list nodes yields
  one shared class — e.g. `ServiceProfile`, `GeoArea`.)

## Regenerating

The source 3GPP YANG modules are **not** redistributed in this repository. To
reproduce this output, obtain the module set from 3GPP and run the converter:

1. **Get the YANG modules.** Download the Release-19 `yang-models/` directory
   (with its required `external-yams/` dependencies) from the 3GPP SA5 forge:

   ```bash
   curl -L -o MnS-Rel-19-yang-models.zip \
     "https://forge.3gpp.org/rep/sa5/MnS/-/archive/Rel-19/MnS-Rel-19.zip?ref_type=heads&path=yang-models"
   ```

   This tracks the current `Rel-19` branch tip, which has grown since this
   snapshot was generated (this snapshot: 501 IOCs; the live branch is larger),
   so regenerating will **not** byte-match the committed files here. That is
   expected — any recent Release-19 revision yields valid output. For the record,
   the archive used for this snapshot had SHA-256
   `7db850aaea7b6078bf62c6318e3cf9a7c3b9d987a7d49047a63ed51098e2de46`.

2. **Run the converter:**

   ```bash
   uv run yang-to-rdf MnS-Rel-19-yang-models.zip \
     -o examples/MnS-Rel-19-yang-models --release Rel-19
   ```

Output is deterministic (byte-identical for the same input and tool version), so
regenerating from the same zip produces no diff. A diff here therefore means
either the source module set or the converter changed — both intentional,
reviewable events.
