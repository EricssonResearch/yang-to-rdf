# yang-to-rdf

Convert YANG modules to RDF TBox vocabularies and SHACL validation shapes.

Designed for 3GPP NRM (TS 28.541) YANG modules but applicable to any YANG schema.

## Install

```bash
uv sync
```

## Usage

**Important:** The converter requires a **complete** YANG module set with its `external-yams/` folder. Single modules or incomplete sets will fail validation. Download complete sets from the [3GPP MnS forge repository](https://forge.3gpp.org/rep/sa5/MnS).

```bash
# Convert the complete MnS Release 19 dataset (recommended)
uv run yang-to-rdf MnS-Rel-19-yang-models.zip

# Or from an extracted directory (must contain the external-yams/ subfolder)
uv run yang-to-rdf MnS-Rel-19-yang-models/yang-models/

# Skip the reference extension layer
uv run yang-to-rdf MnS-Rel-19-yang-models.zip --no-inference

# Output only RDF TBox (no SHACL shapes)
uv run yang-to-rdf MnS-Rel-19-yang-models.zip --format rdf

# Output only SHACL shapes (no RDF TBox)
uv run yang-to-rdf MnS-Rel-19-yang-models.zip --format shacl
```

### Output Files

The converter produces three Turtle files in the output directory (default: `output/`):

1. **`<stem>_rdf.ttl`** — RDFS/OWL TBox vocabulary
   - Classes for IOCs and dataTypes
   - Properties with domain/range
   - Containment relationships (`nrm:nameContains`)
   - Inheritance hierarchy (`rdfs:subClassOf`)

2. **`<stem>_shacl.ttl`** — SHACL validation shapes
   - NodeShapes for each class
   - Property constraints (cardinality, datatype, enums, patterns)
   - Validates instance data against the schema

3. **`<stem>_refs.ttl`** — Reference extension layer (unless `--no-inference`)
   - Inferred `rdfs:range` for DN references (leaf names ending in `Ref`/`RefList`)
   - Provenance metadata: `nrm:inferredBy`, `nrm:confidence` (unambiguous/unresolved)
   - ~121 unambiguous ranges inferred from name patterns (121 for the Rel-19 set; varies by module set)
   - Kept separate for auditability and optional loading

## Design Decisions

### IRI Strategy

Properties are path-scoped to avoid multi-domain conflicts:
- Class: `<module-namespace>/ClassName`
- Property: `<module-namespace>/ClassName/propertyName`

### YANG → RDF Mapping

| YANG construct | RDF output |
|---|---|
| `augment` adding `list X` | `nrm:nameContains` (containment) |
| `uses ManagedFunctionGrp` | `rdfs:subClassOf` (inheritance) |
| `leaf` | `rdf:Property` with `rdfs:domain` + `rdfs:range` |
| `leaf` ending in `Ref`/`RefList` | `owl:ObjectProperty` + `nrm:isReference` (DN reference with open range in base; inferred ranges in `_refs.ttl`) |
| `typedef` | `rdfs:Datatype` |
| `list` inside `attributes` | `rdfs:Class` + `owl:ObjectProperty` + `nrm:hasAttribute` (3GPP <<dataType>> structured attributes) |
| `choice/case` | `sh:xone` in SHACL |

### NRM Vocabulary

A small `nrm:` vocabulary defines 3GPP-specific relationships:
- `nrm:nameContains` — containment hierarchy
- `nrm:ManagedFunction` — base class for all NF IOCs
- `nrm:hasAttribute` — links IOC to structured attribute class (3GPP <<dataType>>)
- `nrm:isReference` — marks DN leaf properties (range inferred separately)
- `nrm:isInvariant` — marks properties with the `inVariant` extension

### DN Reference Inference

3GPP YANG leaves ending in `Ref`, `Refs`, `RefList`, or `List` are Distinguished Name references to other IOCs. The base RDF layer marks these as `nrm:isReference` with an open range (no `rdfs:range` triple). The separate reference extension layer (`_refs.ttl`) infers ranges by stripping suffixes and matching IOC names:

- **Unambiguous** (121 for the Rel-19 set; varies by module set): Single matching IOC → `rdfs:range` triple with `nrm:confidence "unambiguous"`
- **Unresolved**: Zero or multiple matches → no range, `nrm:confidence "unresolved"`, candidate name recorded

This separation keeps the base TBox clean and the inference layer auditable. Load `_refs.ttl` optionally depending on your tolerance for heuristic reasoning.
