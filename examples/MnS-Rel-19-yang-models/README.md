# Reference output — 3GPP MnS Rel-19 YANG models

Committed snapshot of the RDF/SHACL output produced by `yang-to-rdf` for the
3GPP SA5 MnS Release-19 YANG module set. Kept in-repo so consumers can inspect
the vocabulary without running the tool, and so ontology changes are reviewable
as diffs.

**This snapshot is pinned to an immutable upstream tag and reproduces
byte-for-byte.** One command regenerates it exactly (see [Regenerating](#regenerating)).
The previous snapshot was taken from the moving `Rel-19` branch tip and could not
be re-derived by anyone.

## Files

Output is **split one file per source YANG module** (the default) so each file is
small and browsable directly on GitHub. For each module `<m>`:

| File | Contents |
|---|---|
| `<m>_rdf.ttl` | RDFS/OWL ontology (TBox) for that module: IOC classes, 3GPP `<<dataType>>` classes, containment, inheritance, properties |
| `<m>_shacl.ttl` | SHACL NodeShapes for that module's classes |
| `<m>_refs.ttl` | Reference-inference layer for that module's DistinguishedName references (only if it has any) — inferred `rdfs:range` with `y2r:confidence` / `y2r:inferredBy` provenance |
| `index.ttl` | Aggregating ontology: the minted `y2r:` vocabulary + `owl:imports` of every module, plus `owl:versionIRI`/`owl:versionInfo`. Load this to pull in the whole set. |

Cross-module links (e.g. `AMFFunction rdfs:subClassOf y2r:ManagedFunction`,
`ManagedElement y2r:nameContains AMFFunction`, or a property whose range is a
class defined in another module) live in the file of the triple's **subject**
module and resolve by IRI when the set is loaded together. A shared dataType
class (e.g. `ServiceProfile`, `GeoArea`) is defined once in its grouping's home
module and referenced by IRI elsewhere.

To produce a single merged file per layer instead, run with `--single-file`.

## IRIs

Terms use `https` IRIs in a per-module hash namespace, and each module binds its
own YANG `prefix` so the Turtle reads like the source:

```turtle
@prefix amf3gpp: <https://semantics.ericsson.com/yang/_3gpp-5gc-nrm-amffunction#> .

amf3gpp:AMFFunction a rdfs:Class ; rdfs:subClassOf y2r:ManagedFunction .
amf3gpp:AMFFunction.aMFSetRef a owl:ObjectProperty .
```

`semantics.ericsson.com` is an Ericsson-owned namespace minted by this project.
It is **not currently dereferenceable** and asserts no 3GPP endorsement. Pass
`--base-iri` to emit terms under a different authority. Each module ontology
records the YANG namespace it came from, so nothing is lost:

```turtle
<https://semantics.ericsson.com/yang/_3gpp-5gc-nrm-amffunction>
    y2r:yangModuleName "_3gpp-5gc-nrm-amffunction" ;
    y2r:yangNamespace  <urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction> .
```

See [CONVERSION_NOTES.md](../../CONVERSION_NOTES.md) for the full scheme and
[VERSIONING.md](../../VERSIONING.md) for loading multiple releases side by side.

## Provenance

| | |
|---|---|
| Source | 3GPP SA5 MnS forge, <https://forge.3gpp.org/rep/sa5/MnS> |
| Ref | tag **`Tag_Rel19_SA112`** (immutable) |
| Commit | `24ffa42e24c806959fe94cbd3565bc0ffbe4b379` |
| Archive SHA-256 | `0e531961be20f2dd5dc69920eb12b1fd195c31dc59fe81b0ec18df0ec7228b30` |
| Tool | `yang-to-rdf` v0.3.0 |
| Generated | 2026-09-17 |

Model summary, as reported by the converter and by
[`scripts/iri_census.py`](../../scripts/iri_census.py):

| Figure | Value |
|---|---|
| YANG files collected | 130 |
| modules registered | 131 |
| modules emitting terms | 120 |
| IOC classes | 643 |
| `<<dataType>>` classes | 539 |
| typedefs | 139 |
| DN references | 147 unambiguous / 584 unresolved |
| parse errors | 0 |
| output files | 325 (324 per-module + `index.ttl`), largest 136 KB |
| triples | 102,255 |
| distinct terms | 10,234 — 9,042 `yang/`, 1,182 `shapes/`, 10 minted `vocab#` |

`131 = 130 files − 2 submodules + 3 IETF modules`: the two submodules
(`_3gpp-ns-nrm-serviceprofile`, `_3gpp-ns-nrm-sliceprofile`) register under their
parent module via `belongs-to`, and `ietf-inet-types`, `ietf-yang-types` and
`ietf-yang-schema-mount` resolve from the search path rather than the collected
file list. Of the 131, eleven emit no terms — base-grouping and extension-only
modules such as `_3gpp-common-top` and `_3gpp-common-yang-extensions`.

`<<dataType>>` classes are named and shared by their YANG grouping, so a grouping
reused across many list nodes yields one shared class.

## Regenerating

The source 3GPP YANG modules are **not** redistributed in this repository. The
converter fetches them for you from the pinned tag:

```bash
uv run yang-to-rdf --fetch-release Tag_Rel19_SA112 --ref-type tags \
  -o examples/MnS-Rel-19-yang-models
```

This reproduces the committed files **byte-for-byte** — verified by running it
twice into separate directories and diffing, and asserted as a stage of
[`scripts/verify.py`](../../scripts/verify.py), which the Docker image runs.

A diff here therefore means the converter changed, which is an intentional,
reviewable event. To check the output independently:

```bash
uv run python -m scripts.iri_census examples/MnS-Rel-19-yang-models
```

Note that `--fetch-release Rel-19` (a *branch*) tracks the moving tip and will
**not** match: when this snapshot was taken the branch carried 13 modules the tag
does not. Use the tag for reproducibility.
