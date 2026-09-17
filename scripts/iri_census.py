#!/usr/bin/env python3
"""Census + gates over emitted IRIs.

Answers, over real converted output: are all emitted IRIs valid absolute http(s)
URLs, is the term mapping injective, did any URN leak, do the files survive an
rdflib round-trip, does every filename match its module IRI, and is every local
name a legal NCName?

Gate definitions and expectations:
docs/superpowers/specs/2026-09-17-http-iri-scheme-design.md §8.

This script is the SINGLE definition of these figures. Documentation quoting them
names this script; do not re-derive them with an ad-hoc walk, which will quietly
use different rules.

Every gate reports the size of the candidate set it searched. "0 violations out
of 8,171 terms" is a finding; "0 violations" is not.

Usage:
    uv run python -m scripts.iri_census OUTPUT_DIR [--base-iri BASE] [--json PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from rdflib import Graph, URIRef
from rdflib.compare import isomorphic

from yang_to_rdf.namespace import (
    DEFAULT_BASE_IRI,
    NCNAME_RE,
    is_ambiguous_local_name,
    normalize_base_iri,
)

LAYER_SUFFIX = re.compile(r"_(rdf|shacl|refs)$")


@dataclass
class GateResult:
    gate: str
    passed: bool
    checked: int
    violations: list[str] = field(default_factory=list)
    note: str = ""


def load_graphs(output_dir: Path) -> dict[Path, Graph]:
    """Parse every .ttl in the directory. Refuses an empty directory: a gate that
    inspected nothing has not passed, it has not run."""
    graphs: dict[Path, Graph] = {}
    for p in sorted(output_dir.glob("*.ttl")):
        g = Graph()
        g.parse(p, format="turtle")
        graphs[p] = g
    if not graphs:
        raise SystemExit(f"no .ttl files in {output_dir} -- nothing to check")
    return graphs


def all_uris(graphs: dict[Path, Graph]) -> set[str]:
    out: set[str] = set()
    for g in graphs.values():
        for triple in g:
            for term in triple:
                if isinstance(term, URIRef):
                    out.add(str(term))
    return out


def provenance_urns(graphs: dict[Path, Graph]) -> set[str]:
    """URNs retained deliberately as y2r:yangNamespace objects (spec D6).

    G1 and G3 both need this exemption. Deriving it in ONE place is the point: an
    earlier draft had G1 decide independently and it failed on 107 IRIs that the
    design requires, which would have tempted a weakening of the gate.
    """
    out: set[str] = set()
    for g in graphs.values():
        for p in set(g.predicates()):
            if str(p).endswith("#yangNamespace"):
                for o in g.objects(None, p):
                    if isinstance(o, URIRef):
                        out.add(str(o))
    return out


def _ours(uris: set[str], base: str) -> list[str]:
    return sorted(u for u in uris if u.startswith(base))


def _terms(uris: set[str], base: str) -> list[str]:
    """Our IRIs that carry a hash local name, i.e. the vocabulary terms."""
    return [u for u in _ours(uris, base) if "#" in u]


def g1_absolute_http(uris: set[str], exempt: set[str]) -> GateResult:
    """Every emitted IRI is an absolute http(s) URL with an authority.

    `exempt` is the set of provenance URNs the design retains on purpose; they are
    excluded from the candidate set rather than from the rule, and the count of
    exemptions is reported so the exclusion cannot hide a problem.
    """
    candidates = sorted(uris - exempt)
    bad = []
    for u in candidates:
        parts = urlsplit(u)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            bad.append(u)
    return GateResult(
        "G1", not bad, len(candidates), bad[:20],
        f"{len(candidates) - len(bad)}/{len(candidates)} absolute http(s); "
        f"{len(exempt)} provenance URNs exempt by design")


def g2_injective(graphs: dict[Path, Graph], base: str) -> GateResult:
    """The term mapping is injective: no local name has two valid readings.

    A composed local name is `<Class>.<prop>`. It is ambiguous only when it can
    be split at a '.' with BOTH halves legal YANG identifiers in more than one
    way -- see namespace.is_ambiguous_local_name. `xpath1.0` is NOT ambiguous,
    because a property cannot be named `0`.
    """
    terms = _terms(all_uris(graphs), base)
    ambiguous = [t for t in terms if is_ambiguous_local_name(t.rsplit("#", 1)[1])]
    dupes = [u for u, n in Counter(terms).items() if n > 1]
    bad = sorted(ambiguous + dupes)
    return GateResult("G2", not bad, len(terms), bad[:20],
                      f"{len(set(terms))} distinct of {len(terms)} terms, "
                      f"{len(ambiguous)} ambiguous")


def g3_no_urn_leak(graphs: dict[Path, Graph]) -> GateResult:
    """No URN survives except as a y2r:yangNamespace provenance object.

    The count of retained provenance URNs is reported, not just the leaks, so a
    silent LOSS of provenance is as visible as a leak.
    """
    leaked: list[str] = []
    provenance = 0
    for path, g in graphs.items():
        prov_preds = {p for p in set(g.predicates())
                      if str(p).endswith("#yangNamespace")}
        for s, p, o in g:
            for term in (s, p, o):
                if not (isinstance(term, URIRef) and str(term).startswith("urn:")):
                    continue
                if term == o and p in prov_preds:
                    provenance += 1
                else:
                    leaked.append(f"{path.name}: {term} via {p}")
    return GateResult("G3", not leaked, provenance + len(leaked), sorted(leaked)[:20],
                      f"{provenance} provenance URNs retained, {len(leaked)} leaked")


def g4_round_trip(graphs: dict[Path, Graph]) -> GateResult:
    """serialize -> parse -> compare, per file, up to blank-node relabelling.

    Compared with rdflib.compare.isomorphic, NOT set equality. SHACL property
    shapes are blank nodes, and a reparse assigns them fresh labels, so set
    equality reports every _shacl.ttl as differing while the triple counts match
    exactly -- which is what an earlier draft of this gate did.
    """
    bad = []
    for path, g in graphs.items():
        h = Graph()
        h.parse(data=g.serialize(format="turtle"), format="turtle")
        if not isomorphic(g, h):
            bad.append(f"{path.name}: {len(g)} triples in, {len(h)} out, not isomorphic")
    return GateResult("G4", not bad, len(graphs), bad[:20],
                      f"{len(graphs) - len(bad)}/{len(graphs)} files round-trip")


def g7_filename_matches_module(graphs: dict[Path, Graph], base: str) -> GateResult:
    """Each <stem>_<layer>.ttl carries terms of the module named by <stem>."""
    bad = []
    checked = 0
    for path, g in graphs.items():
        if path.name == "index.ttl":
            continue
        stem = LAYER_SUFFIX.sub("", path.stem)
        checked += 1
        expected = f"{base}yang/{stem}"
        shapes = f"{base}shapes/{stem}#"
        subjects = {str(s) for s in g.subjects() if isinstance(s, URIRef)}
        if not any(s == expected or s.startswith(expected + "#") or s.startswith(shapes)
                   for s in subjects):
            bad.append(f"{path.name}: no subject under {expected}")
    return GateResult("G7", not bad, checked, bad[:20],
                      f"{checked - len(bad)}/{checked} filenames match their module")


def g8_ncname_locals(graphs: dict[Path, Graph], base: str) -> GateResult:
    """Every local name is a legal NCName (XML Namespaces, W3C Recommendation)."""
    terms = _terms(all_uris(graphs), base)
    bad = [t for t in terms if not NCNAME_RE.match(t.rsplit("#", 1)[1])]
    return GateResult("G8", not bad, len(terms), sorted(bad)[:20],
                      f"{len(terms) - len(bad)}/{len(terms)} local names are NCNames")


def census(output_dir: Path, base_iri: str = DEFAULT_BASE_IRI) -> list[GateResult]:
    """Run every gate. Adding a gate here without wiring it into the summary is
    caught by tests/test_iri_census.py, which asserts the gate set."""
    base = normalize_base_iri(base_iri)
    graphs = load_graphs(Path(output_dir))
    uris = all_uris(graphs)
    return [
        g1_absolute_http(uris, provenance_urns(graphs)),
        g2_injective(graphs, base),
        g3_no_urn_leak(graphs),
        g4_round_trip(graphs),
        g7_filename_matches_module(graphs, base),
        g8_ncname_locals(graphs, base),
    ]


def corpus_summary(output_dir: Path, base_iri: str = DEFAULT_BASE_IRI) -> dict:
    """The figures quoted in the design doc, with their definitions attached."""
    base = normalize_base_iri(base_iri)
    graphs = load_graphs(Path(output_dir))
    uris = all_uris(graphs)
    ours = _ours(uris, base)
    terms = _terms(uris, base)
    yang_terms = [t for t in terms if t.startswith(f"{base}yang/")]
    shape_terms = [t for t in terms if t.startswith(f"{base}shapes/")]
    # The minted vocabulary is the third bucket. Naming it explicitly matters:
    # yang + shapes alone is 10 short of the total, and that gap is easy to
    # overlook because the two figures look like they should add up.
    vocab_terms = [t for t in terms if t.startswith(f"{base}vocab#")]
    unaccounted = sorted(set(terms) - set(yang_terms) - set(shape_terms)
                         - set(vocab_terms))
    return {
        "files": len(graphs),
        "triples": sum(len(g) for g in graphs.values()),
        "distinct_iris_all": len(uris),
        "distinct_iris_ours": len(ours),
        "terms_total": len(terms),
        "terms_in_yang_namespace": len(yang_terms),
        "terms_in_shapes_namespace": len(shape_terms),
        "terms_in_minted_vocabulary": len(vocab_terms),
        "terms_unaccounted_for": len(unaccounted),
        "distinct_local_names": len({t.rsplit("#", 1)[1] for t in terms}),
        "terms_with_dotted_local_name": len([
            t for t in terms if "." in t.rsplit("#", 1)[1]]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("output_dir", type=Path, help="directory of generated .ttl files")
    ap.add_argument("--base-iri", default=DEFAULT_BASE_IRI)
    ap.add_argument("--json", type=Path, default=None,
                    help="also write the results as JSON")
    a = ap.parse_args(argv)

    results = census(a.output_dir, a.base_iri)
    summary = corpus_summary(a.output_dir, a.base_iri)

    print(f"corpus: {a.output_dir}")
    for k, v in summary.items():
        print(f"  {k:32s} {v:>9,}")
    print()
    print(f"{'gate':6s} {'result':8s} {'checked':>9s}  note")
    for r in results:
        print(f"{r.gate:6s} {'PASS' if r.passed else 'FAIL':8s} "
              f"{r.checked:9,}  {r.note}")
        for v in r.violations:
            print(f"         - {v}")

    if a.json:
        a.json.write_text(json.dumps(
            {"summary": summary, "gates": [asdict(r) for r in results]}, indent=2))

    failed = [r for r in results if not r.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} gates passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
