# Contributing

Contributions are welcome, and the list of [open gaps](#where-help-is-most-useful)
below is the honest one — these are things the maintainers know are missing, not a
wish list. Several are self-contained enough to be a first contribution.

## Getting set up

See [Install](README.md#install). The short version:

```bash
git clone https://github.com/EricssonResearch/yang-to-rdf.git
cd yang-to-rdf
uv sync --locked --group dev
```

## Running the checks

```bash
uv run pytest -m "not slow"     # fast loop while developing (a few seconds)
uv run pytest                   # full suite
uv run ruff check .             # lint; expected to be clean
```

Two checks beyond the unit tests, both worth running before opening a PR:

```bash
# The IRI gates: absolute-http validity, injectivity, no URN leakage, rdflib
# round-trip, filename/module agreement, NCName legality. Reports the size of the
# candidate set it searched, so "0 of 10,234" is a finding and "0" is not.
#
# Takes ~4 minutes on the full corpus. Almost all of it is the round-trip gate
# canonicalising the 118 SHACL files, whose property shapes are blank nodes and so
# cannot be compared by set equality. `uv run pytest tests/test_iri_census.py`
# runs the same gates against a small module subset in seconds, which is the right
# loop while developing; the full run is what CI and the container do.
uv run python -m scripts.iri_census examples/MnS-Rel-19-yang-models

# Everything, from a clean base: install, tests, a wheel installed into a fresh
# virtualenv, conversion of the pinned upstream tag, the gates, and a
# byte-for-byte diff against examples/.
docker build -t yang-to-rdf .
docker run --rm -v "$PWD/examples:/yang-to-rdf/examples:ro" yang-to-rdf
```

## If your change alters the output

`examples/MnS-Rel-19-yang-models/` is a committed snapshot pinned to an immutable
upstream tag, and the container asserts it reproduces byte-for-byte. So any change
to what the converter emits will fail that stage until you regenerate it:

```bash
uv run yang-to-rdf --fetch-release Tag_Rel19_SA112 --ref-type tags \
  -o examples/MnS-Rel-19-yang-models
```

Please include the regenerated diff in the same PR, and say in the description what
changed and by how much. A diff there is a reviewable event, not a nuisance — it is
how a change to the ontology becomes visible.

## What we ask of a change

Nothing unusual, but two things are taken seriously here because the repo has been
bitten by both:

**Say what you measured, not what you expect.** If a change affects the emitted
graph, run it over the real corpus and put the numbers in the PR. `scripts/iri_census.py`
exists so that the figures come from one committed definition rather than an ad-hoc
walk that quietly uses different rules.

**Watch your test fail before trusting it.** Break the thing the test guards,
confirm it goes red, then restore. `docs/superpowers/2026-09-17-gate-inversion-log.md`
records this being done for every existing gate — including two that turned out
*not* to fail and were defective as a result. An assertion nobody has seen fail is
a decoration. If you add a guard, we will ask which failure you observed, not which
assertion you wrote.

## Where help is most useful

Roughly easiest first. Each names the file to start in and the check that would
demonstrate it works.

### Declare the five annotation predicates

`y2r:confidence`, `y2r:inferredBy`, `y2r:candidate`, `y2r:yangModuleName` and
`y2r:yangNamespace` are used but carry no `rdf:type`/`rdfs:comment`, unlike the five
core terms. A strict OWL consumer sees undeclared predicates. See
[CONVERSION_NOTES §1](CONVERSION_NOTES.md#1-the-y2r-vocabulary--the-complete-non-standard-surface).

Start in `yang_to_rdf/rdf_converter.py` (`_emit_vocab`) and
`yang_to_rdf/reference_layer.py`. This changes the output, so `examples/` needs
regenerating.

### Emit `skos:prefLabel`

Every term already carries a globally unique `rdfs:label`, but no SKOS layer is
emitted. Useful for thesaurus-oriented consumers. `yang_to_rdf/rdf_converter.py`
(`_assign_labels`).

### Express `choice`/`case` mutual exclusivity as `sh:xone`

The largest *modelling* gap. YANG `choice`/`case` leaves are currently flattened
onto the owning class — no data is lost, but the "exactly one case" constraint is
not emitted, so a consumer sees all case leaves as optional siblings.
[CONVERSION_NOTES §6](CONVERSION_NOTES.md#6-known-limitations--honest-gaps).

Start in `yang_to_rdf/yang_parser.py` (`_fill_children`, which currently recurses
through `choice`/`case`) and `yang_to_rdf/shacl_converter.py`. Demonstrate it with a
`pyshacl` test in `tests/test_shacl_validation.py`: an instance setting leaves from
two different cases must be **rejected**, and one setting a single case accepted.

### Check the TBox is consistent OWL

**Not done, and nobody has looked.** The RDF layer has never been loaded into an OWL
reasoner. We do not know whether it is consistent, and the honest position is that
"we emit RDFS/OWL vocabulary" is verified while "the ontology is coherent" is not —
the same distinction that applied to the SHACL layer until a real engine was pointed
at it.

A good contribution here would load the merged TBox into a reasoner (HermiT via
`owlready2`, or ROBOT) and report what it finds. Note the design deliberately
asserts no reasoner-dependent semantics — no `owl:inverseOf`, no
`owl:disjointWith`, RDFS `domain`/`range` used descriptively — so it may well be
consistent but uninteresting to a reasoner. Finding that out is the contribution;
please report the result either way rather than only if it is clean.

### Instance-level parity between the YANG and the SHACL

The strongest correctness claim available, and currently out of reach for want of
data. `tests/test_shacl_validation.py` proves the shapes enforce what they
*declare*; it does **not** prove they are equivalent to the source YANG.

Doing it properly means taking a real RESTCONF/NETCONF sample, validating it against
the YANG (`yangson` or `yanglint`) and, converted to RDF, against the SHACL, then
confirming both accept and reject the same instances for the same reasons.
Representative sample data is the blocker.

### Improve the DN reference inference

Cross-object references in 3GPP NRM are `DistinguishedName`-typed strings with no
schema-declared target. Detection is reliable and type-based; the *range* is guessed
by stripping a `Ref`/`RefList` suffix from the leaf name. For the pinned Rel-19 set
that resolves 147 unambiguously and leaves **584 unresolved** — the largest
recall gap in the output. Every guess is quarantined in `*_refs.ttl` and tagged
with `y2r:confidence`, so a better heuristic can be evaluated against the current
one. `yang_to_rdf/reference_layer.py`.

### Ontology documentation that navigates

Rendered HTML documentation (pyLODE) was dropped rather than shipped, because its
navigation did not work with the previous IRI scheme. The scheme has since changed
— every module now has a single hash namespace, which is the shape documentation
tools expect — so this may now work, or work with modest effort. Nobody has
retried it. `scripts/build_docs.py`.

### Serve the namespace

`https://semantics.ericsson.com/` is Ericsson-owned, minted by this project, and
**does not currently resolve**. The scheme was deliberately chosen so that serving
it needs only static files — a hash namespace per module, no 303 redirects and no
content negotiation. See
[CONVERSION_NOTES §1a](CONVERSION_NOTES.md#1a-the-iri-scheme--what-it-rests-on-and-what-is-ours).

Making the IRIs dereferenceable is mostly an infrastructure question rather than a
code one. A `w3id.org` PURL fronting it would also be a reasonable route and would
survive the content moving.

## Things that are deliberate, not oversights

Please read [CONVERSION_NOTES.md](CONVERSION_NOTES.md) before proposing these — each
is a decision with reasoning attached, and we would rather revisit it explicitly
than have it changed as a cleanup:

- **Class identity comes from the YANG `grouping`, not the list node** (§5), so a
  class name may match no single YANG node name.
- **DistinguishedName leaves get no `rdfs:range`** in the base TBox (§3).
  Fabricating one would assert something the schema does not state.
- **3GPP `<<dataType>>` attributes become named classes**, not blank nodes (§4).
- **Properties are class-scoped** (`#Class.property`). 814 of 5,572
  `(module, property)` pairs reuse a name across classes within one module, so a
  flat namespace would silently merge distinct properties. Run
  `scripts/iri_census.py` for the current figures rather than trusting these.
- **No AI-attribution trailers in commit messages.**
