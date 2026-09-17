# yang-to-rdf

Convert YANG modules to RDF TBox vocabularies and SHACL validation shapes.

Designed for 3GPP NRM (TS 28.541) YANG modules but applicable to any YANG schema.

A committed, browsable example of the generated output for the 3GPP SA5 MnS
Release-19 set is in [`examples/`](examples/) — you can inspect the vocabulary
without running the tool. It is pinned to an immutable upstream tag and
**reproduces byte-for-byte**; see
[its README](examples/MnS-Rel-19-yang-models/README.md). The source YANG modules
are **not** redistributed here (see below for how to obtain them).

## Install

Requires Python ≥ 3.10 and [uv](https://docs.astral.sh/uv/), which provisions the
right Python and dependencies from the lockfile:

```bash
git clone https://github.com/EricssonResearch/yang-to-rdf.git
cd yang-to-rdf
uv sync --locked
```

The [`Dockerfile`](Dockerfile) runs **exactly these commands** from a clean
`python:3.12-slim` base, and a test asserts that correspondence, so these
instructions cannot go stale. The container substitutes `COPY` for the
`git clone` line — that is the only difference.

## Verifying that it all reproduces

One command builds a clean image and runs every check: install from the lockfile,
the unit suite, a wheel build installed into a fresh virtualenv, conversion of the
pinned upstream tag, the IRI gates, and a byte-for-byte diff against
[`examples/`](examples/).

```bash
docker build -t yang-to-rdf .
docker run --rm -v "$PWD/examples:/yang-to-rdf/examples:ro" yang-to-rdf
```

`examples/` is excluded from the build context to keep the image small, hence the
read-only mount for the reproducibility stage.

Without access to the 3GPP forge, the stages that need it **fail** rather than
skip. To run only the offline stages, ask for it explicitly — the summary then
reports `INCOMPLETE` rather than success:

```bash
docker run --rm yang-to-rdf --offline
```

The same entry point works on a host checkout: `uv run python -m scripts.verify`.

## Getting the YANG modules

This tool does not ship 3GPP YANG. 3GPP SA5 publishes the MnS YANG models at
<https://forge.3gpp.org/rep/sa5/MnS>. Download the Release-19 `yang-models/`
directory as a zip (it bundles the `external-yams/` IETF dependencies the models
import) and pass that zip straight to the converter — no repacking needed:

The converter can fetch the set for you — just name a branch or tag:

```bash
# Branch (default --ref-type heads); also stamps the output with release "Rel-19"
uv run yang-to-rdf --fetch-release Rel-19

# A specific tag
uv run yang-to-rdf --fetch-release Tag_Rel20_SA112 --ref-type tags
```

Or download the zip yourself and pass it in:

```bash
curl -L -o yang-models.zip \
  "https://forge.3gpp.org/rep/sa5/MnS/-/archive/Rel-19/MnS-Rel-19.zip?ref_type=heads&path=yang-models"
uv run yang-to-rdf yang-models.zip -o output/
```

`--fetch-release` pulls the current tip of the named ref, so the exact class
counts track upstream and won't byte-match the committed [`examples/`](examples/)
snapshot — any recent revision yields valid output. Because 3GPP YANG namespaces
(and therefore the generated IRIs) are stable across releases, use `--release`
(auto-set by `--fetch-release`) to tag each run so releases can be told apart —
see [VERSIONING.md](VERSIONING.md).

## Usage

**Important:** The converter requires a **complete** YANG module set with its `external-yams/` folder. Single modules or incomplete sets will fail validation.

```bash
# Convert the complete MnS Release 19 dataset (recommended)
uv run yang-to-rdf MnS-Rel-19-yang-models.zip

# Choose the output directory (default: output/)
uv run yang-to-rdf MnS-Rel-19-yang-models.zip -o build/

# Or from an extracted directory (must contain the external-yams/ subfolder)
uv run yang-to-rdf MnS-Rel-19-yang-models/yang-models/

# Tag the output with a release label (owl:versionIRI / owl:versionInfo)
uv run yang-to-rdf MnS-Rel-19-yang-models.zip --release Rel-19

# One merged file per layer instead of per-module split files
uv run yang-to-rdf MnS-Rel-19-yang-models.zip --single-file

# Skip the reference extension layer
uv run yang-to-rdf MnS-Rel-19-yang-models.zip --no-inference

# Output only RDF TBox (no SHACL shapes)
uv run yang-to-rdf MnS-Rel-19-yang-models.zip --format rdf

# Output only SHACL shapes (no RDF TBox)
uv run yang-to-rdf MnS-Rel-19-yang-models.zip --format shacl
```

### Output Files

The converter produces three **layers** of Turtle output. By default each layer is
**split into one file per source YANG module** (`<module>_rdf.ttl`,
`<module>_shacl.ttl`, `<module>_refs.ttl`) plus an `index.ttl` that carries the
shared `nrm:` vocabulary and `owl:imports` every module — so files stay small and
browsable. Pass `--single-file` to instead get one merged file per layer
(`<stem>_rdf.ttl`, etc.). The three layers:

1. **RDF layer (`…_rdf.ttl`)** — RDFS/OWL TBox vocabulary
   - Classes for IOCs and dataTypes
   - Properties with domain/range
   - Containment relationships (`nrm:nameContains`)
   - Inheritance hierarchy (`rdfs:subClassOf`)

2. **SHACL layer (`…_shacl.ttl`)** — SHACL validation shapes
   - NodeShapes for each class
   - Property constraints (cardinality, datatype, enums, patterns)
   - Validates instance data against the schema

3. **Reference layer (`…_refs.ttl`)** — reference extension (unless `--no-inference`)
   - Inferred `rdfs:range` for DistinguishedName references (detected by type; ranges guessed from the leaf name — see [DN Reference Inference](#dn-reference-inference))
   - Provenance metadata: `nrm:inferredBy`, `nrm:confidence` (unambiguous/unresolved)
   - ~121 unambiguous ranges inferred from name patterns (121 for the Rel-19 set; varies by module set)
   - Kept separate for auditability and optional loading

A committed reference snapshot for the MnS Rel-19 set lives in
[`examples/MnS-Rel-19-yang-models/`](examples/MnS-Rel-19-yang-models/) (per-module
files + `index.ttl`; see its README for provenance). Output is deterministic, so
regenerating from the same input produces no diff.

## Design Decisions

For a full audit of where the conversion follows RDF/OWL/SHACL standards and
where it introduces its own conventions (the `nrm:` vocabulary and a few
modelling choices), see [CONVERSION_NOTES.md](CONVERSION_NOTES.md).

For how this tool fits the broader semantic network management picture and how it
relates to intent-driven management (including why it supersedes the TMF
connector-model approach to 3GPP), see
[docs/SEMANTIC_NETWORK_MANAGEMENT.md](docs/SEMANTIC_NETWORK_MANAGEMENT.md).

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
| `leaf` typed as `DistinguishedName`/`Dn`/`LDN` | `owl:ObjectProperty` + `nrm:isReference` (DN reference with open range in base; inferred ranges in `_refs.ttl`) |
| `typedef` | `rdfs:Datatype` |
| `list` inside `attributes` | `rdfs:Class` + `owl:ObjectProperty` + `nrm:hasAttribute` (3GPP <<dataType>> structured attributes) |
| `choice`/`case` leaves | flattened onto the owning class (mutual-exclusivity is not currently emitted as `sh:xone`) |

### NRM Vocabulary

A small `nrm:` vocabulary defines 3GPP-specific relationships:
- `nrm:nameContains` — containment hierarchy
- `nrm:ManagedFunction` — base class for all NF IOCs
- `nrm:hasAttribute` — links IOC to structured attribute class (3GPP <<dataType>>)
- `nrm:isReference` — marks DN leaf properties (range inferred separately)
- `nrm:isInvariant` — marks properties with the `inVariant` extension

### DN Reference Inference

Detection and range inference are two separate steps:

1. **Detection (by type, reliable):** a leaf is treated as a Distinguished Name reference when its resolved type chain bottoms out at `DistinguishedName`, `Dn`, or `LDN`. The base RDF layer marks these as `owl:ObjectProperty` + `nrm:isReference` with an open range (no `rdfs:range` triple). This does not rely on the leaf name.
2. **Range inference (by name, heuristic):** the separate reference extension layer (`_refs.ttl`) guesses the target IOC by stripping a trailing `Ref`, `Refs`, `RefList`, or `List` from the leaf name and matching against IOC class names:

- **Unambiguous** (121 for the Rel-19 set; varies by module set): Single matching IOC → `rdfs:range` triple with `nrm:confidence "unambiguous"`
- **Unresolved**: Zero or multiple matches → no range, `nrm:confidence "unresolved"`, candidate name recorded

This separation keeps the base TBox clean and the inference layer auditable. Load `_refs.ttl` optionally depending on your tolerance for heuristic reasoning.
