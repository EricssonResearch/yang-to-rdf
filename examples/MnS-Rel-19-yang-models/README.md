# Reference output — 3GPP MnS Rel-19 YANG models

Committed snapshot of the RDF/SHACL output produced by `yang-to-rdf` for the
complete 3GPP SA5 MnS Release 19 YANG module set. Kept in-repo as a reference
so consumers can inspect the vocabulary without running the tool, and so
changes to the ontology are reviewable as diffs.

## Files

| File | Contents |
|---|---|
| `MnS-Rel-19-yang-models_rdf.ttl` | RDFS/OWL ontology (TBox): IOC classes, 3GPP `<<dataType>>` classes, containment, inheritance, properties (~69,107 triples) |
| `MnS-Rel-19-yang-models_shacl.ttl` | SHACL NodeShapes for every class (~123,533 triples) |
| `MnS-Rel-19-yang-models_refs.ttl` | Auditable reference-inference layer: inferred `rdfs:range` for DistinguishedName references, with `nrm:confidence` / `nrm:inferredBy` provenance (~1,845 triples) |

## Provenance

- Source: `MnS-Rel-19-yang-models.zip` (SHA-256 `7db850aaea7b6078bf62c6318e3cf9a7c3b9d987a7d49047a63ed51098e2de46`).
  Obtain 3GPP SA5 YANG from <https://forge.3gpp.org/rep/sa5/MnS>.
- Tool: `yang-to-rdf` v0.2.0.
- Command: `uv run yang-to-rdf MnS-Rel-19-yang-models.zip -o examples/MnS-Rel-19-yang-models`
- Generated: 2026-07-03.
- Model summary: 501 IOCs, 445 dataType classes, 138 typedefs; reference layer
  121 unambiguous / 443 unresolved DN references. (dataType classes are named and
  shared by their YANG grouping, so a grouping reused across many list nodes yields
  one shared class — e.g. `ServiceProfile`, `GeoArea`.)

## Regenerating

Output is deterministic (byte-identical for the same input), so regenerating
from the same zip with the same tool version produces no diff:

```bash
uv run yang-to-rdf MnS-Rel-19-yang-models.zip -o examples/MnS-Rel-19-yang-models
```

A diff here therefore means either the source module set or the converter
changed — both intentional, reviewable events.
