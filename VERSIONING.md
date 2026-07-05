# Versioning RDF/OWL Releases

This document explains how the `yang-to-rdf` tool handles versioning and how to work with multiple releases of 3GPP NRM ontologies.

## Why IRIs are release-agnostic

By design, class and property IRIs in the generated RDF **do not change across releases**. The YANG `namespace` URN for a module (e.g., `urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction`) remains stable from Rel-19 to Rel-20 and beyond, per RFC 7950. We mirror this stability in the RDF output.

This is **correct and intentional**:
- The same concept (e.g., `AMFFunction`) across releases should have the same IRI to enable cross-release comparison, reasoning, and migration queries.
- It matches OWL best practices: stable ontology IRI + changing `owl:versionIRI` to distinguish releases.

However, this creates a **footgun** if mishandled: loading two releases into the same RDF graph will silently merge (union) them, making it impossible to tell which properties came from which release.

## The footgun: naive single-graph loading

If you load Rel-19 and Rel-20 into one default graph:

```turtle
# Naive load (DON'T DO THIS for multi-release comparison)
@prefix amf: <urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/> .

amf:AMFFunction a rdfs:Class ;
    rdfs:comment "..." ;
    # UNION of all properties from both releases - can't tell them apart!
    amf:nFType rdfs:domain amf:AMFFunction ;
    amf:newAttributeInRel20 rdfs:domain amf:AMFFunction .
```

You've lost release provenance. Queries like "what changed in Rel-20?" are now impossible.

## The correct pattern: named graphs

Load each release into its own **named graph**, using the release's `owl:versionIRI` as the graph name:

```turtle
# index.ttl from Rel-19
<https://3gpp.org/nrm/ontology> a owl:Ontology ;
    owl:versionIRI <https://3gpp.org/nrm/ontology/version/Rel-19> ;
    owl:versionInfo "Rel-19" .

# index.ttl from Rel-20
<https://3gpp.org/nrm/ontology> a owl:Ontology ;
    owl:versionIRI <https://3gpp.org/nrm/ontology/version/Tag_Rel20_SA112> ;
    owl:versionInfo "Tag_Rel20_SA112" .
```

Each module ontology also gets `owl:versionInfo` from its YANG `revision` statement:

```turtle
# _3gpp-5gc-nrm-amffunction_rdf.ttl
<urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction> a owl:Ontology ;
    owl:versionInfo "revision 2026-05-25 (CR-1702)" .
```

### Loading recipe

1. Download or generate a release with `--release LABEL`:
   ```bash
   yang-to-rdf --fetch-release Rel-19 -o rel19/
   yang-to-rdf --fetch-release Tag_Rel20_SA112 --ref-type tags -o rel20/
   ```

2. Load each release into a named graph = its `versionIRI`:
   ```python
   from rdflib import Dataset

   ds = Dataset()
   ds.parse("rel19/index.ttl", format="turtle",
            publicID="https://3gpp.org/nrm/ontology/version/Rel-19")
   ds.parse("rel20/index.ttl", format="turtle",
            publicID="https://3gpp.org/nrm/ontology/version/Tag_Rel20_SA112")
   ```

   Or with SPARQL LOAD:
   ```sparql
   LOAD <file:///path/to/rel19/index.ttl> INTO GRAPH <https://3gpp.org/nrm/ontology/version/Rel-19>
   LOAD <file:///path/to/rel20/index.ttl> INTO GRAPH <https://3gpp.org/nrm/ontology/version/Tag_Rel20_SA112>
   ```

3. Query across releases. Example: "What properties were added to `AMFFunction` in Rel-20?"
   ```sparql
   PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

   SELECT ?p WHERE {
     GRAPH <https://3gpp.org/nrm/ontology/version/Tag_Rel20_SA112> {
       ?p rdfs:domain <urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction>
     }
     FILTER NOT EXISTS {
       GRAPH <https://3gpp.org/nrm/ontology/version/Rel-19> {
         ?p rdfs:domain <urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction>
       }
     }
   }
   ```

## How the tool tags releases

### `--release LABEL`

Records the label as:
- `owl:versionIRI` on the aggregate ontology `<https://3gpp.org/nrm/ontology>` (in `index.ttl`).
- `owl:versionInfo` on the aggregate ontology.
- Per-module `owl:versionInfo` from each YANG module's `revision` statement (date + CR reference).

Example:
```bash
yang-to-rdf input/ --release Rel-19 -o output/
```

Produces `index.ttl`:
```turtle
<https://3gpp.org/nrm/ontology> a owl:Ontology ;
    owl:versionIRI <https://3gpp.org/nrm/ontology/version/Rel-19> ;
    owl:versionInfo "Rel-19" .
```

And each module file (e.g., `_3gpp-5gc-nrm-amffunction_rdf.ttl`):
```turtle
<urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction> a owl:Ontology ;
    owl:versionInfo "revision 2026-05-25 (CR-1702)" .
```

### `--fetch-release REF`

Auto-downloads the `yang-models` subtree from the 3GPP forge for a branch or tag:
```bash
yang-to-rdf --fetch-release Rel-19 -o output/
yang-to-rdf --fetch-release Tag_Rel20_SA112 --ref-type tags -o output/
```

If `--release` is not explicitly given, it defaults to the fetched ref name.

## Important caveat: revision date alone is not unique

Multiple releases can share the same YANG `revision` date. For example:
- Rel-19's `_3gpp-5gc-nrm-amffunction`: `revision 2026-05-25 (CR-1702)`
- Rel-20's `_3gpp-5gc-nrm-amffunction`: `revision 2026-05-25 (CR-1703)`

The date is identical; only the CR differs. This means:
- **The user-supplied `--release` label is the canonical discriminator** for queries and named graphs.
- Module-level `versionInfo` is for human readability and tracking individual module changes, not for distinguishing entire releases.

## When you DO want distinct per-release IRIs

If you need each release to have **physically distinct IRIs** (e.g., to load everything into a single default graph without collision), use `--base-namespace` to rewrite the URN prefix:

```bash
yang-to-rdf input/ --base-namespace "https://example.com/nrm/rel19/" -o rel19/
yang-to-rdf input/ --base-namespace "https://example.com/nrm/rel20/" -o rel20/
```

This produces:
- Rel-19: `<https://example.com/nrm/rel19/AMFFunction>`
- Rel-20: `<https://example.com/nrm/rel20/AMFFunction>`

**Trade-off**: You gain collision-free coexistence in one graph, but **lose cross-release identity**. The same concept now has different IRIs, preventing direct comparison and OWL reasoning across releases. Use this only if you truly need separate IRI spaces (e.g., for publishing multiple releases as independent datasets on a public SPARQL endpoint).

## Summary: best practices

1. **Use `--release LABEL`** when generating output so each release has a `versionIRI`.
2. **Load each release into a named graph** = its `versionIRI`. Never load multiple releases into the same default graph.
3. **Use SPARQL named-graph queries** (GRAPH clause) to compare releases, compute diffs, or partition data.
4. **Rely on the release label**, not module revision dates, as the unique release key.
5. **Only use `--base-namespace`** if you absolutely need distinct IRIs per release and can sacrifice cross-release reasoning.

For more on the tool's output structure (split vs single-file, layers, etc.), see the main `README.md`.
