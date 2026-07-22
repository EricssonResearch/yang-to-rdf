#!/usr/bin/env python3
"""Generate browsable HTML documentation for the ontology with pyLODE.

The converter emits every module as its own `owl:Ontology` (correct for the
split output), so a merged graph has ~100 ontologies. A documentation tool needs
a single subject ontology, so this script:

  1. runs the converter in --single-file mode to get one merged RDF TBox,
  2. demotes each per-module `owl:Ontology` to an `owl:imports` of the aggregate
     `https://3gpp.org/nrm/ontology` (which keeps every class/property but leaves
     exactly one ontology for the tool to document),
  3. renders HTML with pyLODE.

Usage:
    python scripts/build_docs.py <input.zip|dir|--fetch-release REF ...> \
        [--release LABEL] -o public/index.html

Any converter args after `--` are passed through to yang-to-rdf; typical CI use:
    python scripts/build_docs.py --fetch-release Rel-19 -o public/index.html
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from yang_to_rdf.input_handler import collect_yang_files, fetch_forge_release
from yang_to_rdf.output_writer import INDEX_ONTOLOGY, stamp_versions
from yang_to_rdf.rdf_converter import YangToRDFConverter
from yang_to_rdf.yang_parser import parse


def build_doc_graph(model, release_label: str | None) -> Graph:
    """Merged TBox with a single documentable ontology (the aggregate)."""
    g = YangToRDFConverter(model).convert()
    stamp_versions(g, model, release_label=release_label, aggregate=True)
    # Collapse the many module ontologies into imports of the aggregate so the
    # documentation tool has exactly one subject ontology.
    for s in list(g.subjects(RDF.type, OWL.Ontology)):
        if s != INDEX_ONTOLOGY:
            g.remove((s, RDF.type, OWL.Ontology))
            g.add((INDEX_ONTOLOGY, OWL.imports, s))
    return g


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", nargs="*", help="Path(s) to .yang, directory, or .zip")
    p.add_argument("--fetch-release", dest="fetch_release", default=None,
                   help="Download yang-models for this 3GPP forge ref")
    p.add_argument("--ref-type", choices=["heads", "tags"], default="heads")
    p.add_argument("--release", default=None, help="Release/version label")
    p.add_argument("--output", "-o", default="public/index.html")
    args = p.parse_args()

    if args.fetch_release:
        args.input = [fetch_forge_release(args.fetch_release, args.ref_type)]
        if not args.release:
            args.release = args.fetch_release
    if not args.input:
        print("Error: provide input or --fetch-release", file=sys.stderr)
        sys.exit(1)

    yang_files, search_paths = collect_yang_files(args.input)
    model, errors = parse(yang_files, search_paths)
    if errors:
        print(f"WARNING: {len(errors)} validation issue(s); docs may be incomplete",
              file=sys.stderr)

    graph = build_doc_graph(model, args.release)

    # Import lazily so the converter/tests don't depend on pyLODE.
    from pylode import OntPub

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".ttl", delete=False) as tmp:
        graph.serialize(destination=tmp.name, format="turtle")
        OntPub(ontology=tmp.name).make_html(destination=str(out))
    print(f"Ontology docs -> {out} ({len(model.classes)} classes documented)")


if __name__ == "__main__":
    main()
