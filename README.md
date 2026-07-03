# yang-to-rdf

Convert YANG modules to RDF TBox vocabularies and SHACL validation shapes.

Designed for 3GPP NRM (TS 28.541) YANG modules but applicable to any YANG schema.

## Install

```bash
uv sync
```

## Usage

```bash
# From a 3GPP zip
uv run yang-to-rdf 28541-k20.zip

# From a directory (e.g. 3GPP forge clone)
uv run yang-to-rdf /path/to/yang/modules/

# With custom namespace
uv run yang-to-rdf 28541-k20.zip --base-namespace https://3gpp.org/nrm/

# Output only RDF (no SHACL)
uv run yang-to-rdf 28541-k20.zip --format rdf
```

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
| `typedef` | `rdfs:Class` |
| `choice/case` | `sh:xone` in SHACL |

### NRM Vocabulary

A small `nrm:` vocabulary defines 3GPP-specific relationships:
- `nrm:nameContains` / `nrm:nameContainedBy` — containment
- `nrm:ManagedFunction` — base class for all NF IOCs
