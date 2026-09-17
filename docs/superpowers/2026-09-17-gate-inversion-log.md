# Gate inversion log — HTTP IRI scheme

_2026-09-17. Every guard added on the `http-iri-scheme` branch was deliberately
broken and watched to fail before being trusted. This records the edit and the
observed result._

A gate nobody has watched fail is a decoration. Two of the eleven inversions below
did **not** fail on the first attempt, and both were real defects in the guard
rather than good news.

## Summary

| # | Guard | Inversion | Result |
|---|---|---|---|
| A | G3 — no URN leaks | `module_iri` returns the YANG namespace URN | **3 tests failed** |
| B | G8 — NCName legality | `NCNAME_RE` loosened to `.*` | **7 tests failed** |
| C | G6 — shapes namespace | shapes namespace collapsed into the class namespace | **passed at first — guard was wrong**, see below |
| D | G2 — injectivity | `is_ambiguous_local_name` always returns `False` | **1 test failed** |
| E | verify stage count | a stage added to `STAGES` and nothing else | **passed at first — guard was tautological**, see below |
| F | prefix-binding cost | `bind_used_prefixes` binds everything | **2 tests failed** |
| G | G9 — scope separator | separator refusal deleted | **3 tests failed** |
| H | install-doc drift | `uv sync --locked` weakened to `uv sync` in the Dockerfile | **3 tests failed** |
| I | publication hygiene | internal hostname reintroduced into `README.md` | **3 tests failed** |
| J | G4 — round-trip | asserted in both directions in `tests/test_iri_census.py` | rejects real differences, tolerates only blank-node relabelling |
| K | corpus partition | (fired on its own, unprompted) | **failed: 203 ≠ 180 + 13** |

## The two that did not fail

### C — the guard was testing the previous design's collision

`test_shapes_live_in_a_separate_namespace` asserted
`class_iri("FooShape") != shape_iri("Foo")`. Collapsing the shapes namespace into
the class namespace did not break it, because `#FooShape` and `#Foo` differ as
strings regardless of which namespace they sit in.

The assertion had been carried over from the old scheme, where a shape IRI *was*
the class name with `Shape` appended. Under the current scheme `shape_iri` uses
the bare class name, so the collision actually available is **the shape of `X`
being the class `X`**. The test now asserts that, plus `nb != sb`, and keeps the
old hazard covered too. Re-inverted: **3 tests fail** (one in
`test_namespace.py`, two in `test_shacl_converter.py`).

Lesson: an inversion that cannot fail is a finding about the *sample*, not a pass.

### E — the count was computed from the thing it counted

`STAGE_COUNT = len(STAGES) + 1`, and `all_stage_names()` also derives from
`STAGES`. So `assert len(all_stage_names()) == STAGE_COUNT` compared a value to
itself and could never fire. Adding a stage silently kept it green — precisely the
failure the guard existed to prevent.

`STAGE_COUNT` is now a hand-typed literal (`8`), so adding a stage forces a
deliberate edit. The test additionally asserts that `STAGE_COUNT = len(` does not
appear in `verify.py`, so the tautology cannot be reintroduced. Re-inverted:
**`test_stage_count_matches_the_stages_defined` fails**.

Lesson: a count assertion whose expected value is derived from its subject is a
decoration. This was the guard I was most confident in.

## Guards that fired unprompted

Worth recording separately, because these were not planned inversions — they
caught defects during ordinary development, which is the stronger evidence:

- **G1 failed on real data**, on 107 IRIs the design requires (the
  `y2r:yangNamespace` provenance URNs). G1 and G3 now share one
  `provenance_urns()` definition rather than each deciding independently. Had G1
  been written more loosely, the tempting fix would have been to weaken it.
- **G4 failed on every `_shacl.ttl`** while reporting matching triple counts
  (`270 in, 270 out`). Cause: SHACL property shapes are blank nodes, relabelled on
  reparse, so set equality was the wrong comparison. Now uses
  `rdflib.compare.isomorphic`.
- **The corpus partition assertion failed 203 ≠ 180 + 13.** The minted `y2r:`
  vocabulary was a third bucket and unnamed. The same slip had passed unnoticed in
  prose minutes earlier, where "8,181 = 7,225 + 946" was read as reconciling
  (it sums to 8,171).
- **The install-doc guard caught an undeclared substitution.** `cd yang-to-rdf` is
  in the README but the Dockerfile uses `WORKDIR`. Declared explicitly rather than
  loosening the check.
- **The Docker wheel stage caught a version mismatch**: `pyproject.toml` said
  `0.2.0` while `--version` said `0.3.0`. No unit test covered packaging metadata.

## Gates that real 3GPP YANG cannot reach

Recorded so a green suite is not read as coverage it does not have. Each is
fixture-driven, and each test docstring says so:

| Gate | Why unreachable on this corpus |
|---|---|
| G5 — YANG identifier validity | 0 of 7,225 local names are invalid |
| G6 — shape/class collision | 0 of 535 class names end in `Shape` |
| G9 — separator ambiguity | 0 of 10,234 composed local names are ambiguous |
| prefix collision handling | 118 modules, 118 distinct YANG prefixes, 0 collisions |

The `xpath1.0` case is the counter-example that matters: the first draft of G9
refused every identifier containing `.`, which would have broken the IETF
`ietf-yang-types` module that nearly every 3GPP module imports. Measured over the
full 7,225-name candidate set — not the filtered 1,482-name subset quoted
earlier, which excluded typedefs owning no properties and therefore *could not*
have found it.

## Reproducing

```bash
uv run pytest -m "not slow"                              # fast loop, ~6s per file
uv run pytest                                            # full suite
uv run python -m scripts.iri_census examples/MnS-Rel-19-yang-models
docker build -t yang-to-rdf . && docker run --rm \
  -v "$PWD/examples:/yang-to-rdf/examples:ro" yang-to-rdf
```
