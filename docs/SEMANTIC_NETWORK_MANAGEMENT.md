# yang-to-rdf in semantic network management, and its relation to intents

This note positions `yang-to-rdf` in the broader **semantic network management**
picture and explains how it relates to **intent-driven management**. It is
conceptual context, not usage — for what the tool emits and the modelling calls it
makes, see [README.md](../README.md) and
[CONVERSION_NOTES.md](CONVERSION_NOTES.md).

## What yang-to-rdf is, in one line

It turns a 3GPP NRM YANG module set (TS 28.541 and friends) into a **native RDF
ontology** — RDFS/OWL classes and properties (the TBox) plus SHACL shapes —
deterministically and completely, without a human hand-authoring the vocabulary.

A 28.541 attribute such as the per-UE downlink throughput becomes a real IRI in the
graph:

```
urn:3gpp:sa5:_3gpp-ns-nrm-networkslice/ServiceProfile/dLThptPerUE
```

with its structure preserved (it ranges onto `…/XLThpt`, which itself carries
`guaThpt`/`maxThpt`), a small `nrm:` vocabulary for the 3GPP-specific relations
(`nrm:nameContains`, `nrm:hasAttribute`, `nrm:isReference`, `nrm:ManagedFunction`),
and SHACL to validate instance data. See [`examples/`](../examples/) for a
committed, browsable output of the full SA5 MnS Release-19 set.

## The semantic network management picture

The thesis of semantic network management is that the integration problem —
TMF business APIs, 3GPP network specs, and vendor APIs all speaking different
"languages" — becomes a **knowledge-graph problem**: different sources are
different views onto one graph, and operational questions become graph queries and
reasoning. A common shape for such a stack:

```
┌───────────────────────────────────────────────────────────────┐
│  Query & Reasoning     — SPARQL, RCA, intent conformance        │
├───────────────────────────────────────────────────────────────┤
│  Semantic lifting      — JSON/API responses → RDF, keyed to a   │
│                          shared vocabulary (the TBox)           │
├───────────────────────────────────────────────────────────────┤
│  Schema foundation     — source schemas → TBox (RDFS/OWL/SHACL) │  ← yang-to-rdf
└───────────────────────────────────────────────────────────────┘
```

**yang-to-rdf sits at the schema-foundation layer, for the 3GPP domain.** It
supplies the *shared vocabulary* that everything above keys on: lifted instance
data (a UPF, a cell, a slice, a service profile) resolves its meaning to the IRIs
this tool mints, and cross-domain joins (TMF service ↔ 3GPP function ↔ vendor
resource) close *because* the 3GPP side is now first-class RDF rather than opaque
YANG. It is an **offline / build-time** step: run rarely, consumed everywhere.

Two properties make it suitable as a foundation rather than a one-off script:

- **Completeness** — it emits the whole module set (every IOC, every structured
  dataType), not a hand-picked subset, so the vocabulary does not silently omit the
  attribute a downstream query needs.
- **Determinism / traceability** — the IRIs map 1:1 to the source YANG
  (`urn:3gpp:sa5:<module>/<Class>/<attr>`), so the ontology regenerates identically
  from the spec and every term is traceable to its origin.

## How this relates to intents

Intent-driven management (3GPP TS 28.312; TM Forum TIO / Intent Common Model)
expresses goals as machine-evaluable expectations — *"downlink throughput per UE
≥ 10 Mbps," "latency ≤ 80 ms"* — and checks them against observed values. In the
TIO model an expectation condition looks like:

```turtle
quan:atLeast ( [ met:lastValue ( <a metric> ) ] "10Mbps"^^quan:quantity )
```

The attributes those intents bound — throughput, latency, number of UEs — are
**exactly the 28.541 NRM attributes yang-to-rdf emits.** So this tool provides the
vocabulary an intent layer needs to *refer to* network attributes by stable IRI.
Two consequences are worth stating precisely.

### 1. yang-to-rdf supersedes the "connector" approach to 3GPP

TM Forum's Intent-toolkit connects 3GPP into the RDF/intent world via **connector
models** (TR293, and its 3GPP instances TR294B for TS 28.541 and TR294A for
TS 28.312). Their stated reason for existing is that 3GPP is **not RDF-native**:
the connector hand-authors a thin RDF *proxy* class per attribute, keyed by a
`Model Element Label` string that points back at the opaque YANG.

yang-to-rdf removes that premise. It makes 28.541 first-class RDF directly, so the
proxy has nothing left to proxy — and the native output is more complete (whole
module set vs a curated subset) and structurally faithful (real nested `XLThpt`
vs proxy *individuals* for the guaranteed/maximum split). For the **artifact /
vocabulary layer**, native RDF *supersedes* the connector model; the connector's
IRIs become at most an optional `owl:equivalentClass` interop target emitted
outward, not a dependency.

### 2. What still has to be added on top: the observation typing

Superseding the connector's *proxying* does not, by itself, make an attribute
usable in an intent expression. The TIO ontology (MetricsAndObservations,
QuantityOntology) requires two distinct, orthogonal typings:

| Slot in an expectation | Required TIO type | Role |
|---|---|---|
| `met:lastValue( X )` | **`X` is a `met:Metric`** | *what* is observed |
| `quan:atLeast/atMost( value, bound )` | value and bound are **`quan:Quantity`** | the *bound* to compare against |

`met:Metric` and `quan:Quantity` are **not** linked in the TIO source — an attribute
must be typed a `met:Metric` to be a legal `met:lastValue` argument, independently
of any `Quantity` typing on the comparison side. yang-to-rdf deliberately emits the
**plain domain ontology** (an attribute is an `rdf:Property` / dataType class) and
stops there: this observation/comparison typing is *intent-layer semantics*, not
network-model structure, so it belongs to a thin overlay applied by the consumer —
not baked into the domain vocabulary. Keeping that boundary is what lets the same
TBox serve inventory queries, validation, and reasoning without presupposing an
intent framework.

### 3. Requirement vs. measurement — where yang-to-rdf stops

28.541 (which this tool covers) is the **requirement / configuration** vocabulary:
what a slice must deliver. Observed **KPIs** (3GPP PM, TS 28.552 — RAN delay,
UE throughput, UPF packet drop) and their aggregation into E2E KQIs are a
*different* layer, not in 28.541, and therefore not produced here. A full intent
loop (requirement → observed KPI → conformance verdict) needs that assurance layer
alongside this one; yang-to-rdf provides the requirement side and the stable IRIs
the KPI side aligns to.

## Boundaries (what yang-to-rdf does not do)

- It does not lift instance data, run SPARQL, or evaluate intents — it produces the
  vocabulary those steps use.
- It does not emit TIO/ICM typing (`met:Metric`, `quan:Quantity`, expectations) —
  see §2; that is an intent-layer overlay.
- It covers the 28.541 NRM (requirement) layer, not 28.552 PM (assurance) — see §3.
- It targets 3GPP NRM but is not 3GPP-specific by construction; the `nrm:`
  vocabulary is the only 3GPP-shaped surface (see CONVERSION_NOTES).

## Summary

yang-to-rdf is the schema-foundation component for the 3GPP domain in a semantic
network management stack: it converts 3GPP NRM YANG into complete, deterministic,
traceable RDF. Because it makes 3GPP RDF-native, it supersedes the connector-model
workaround the intent standards use for a non-RDF 3GPP — while intentionally
leaving the intent-specific observation typing (`met:Metric` / `quan:Quantity`) and
the assurance/KPI layer (28.552) to the layers above, which key onto the IRIs it
mints.
