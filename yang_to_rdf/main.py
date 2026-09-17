"""CLI entry point for yang-to-rdf."""
import argparse
import os
import sys
from pathlib import Path

from rdflib import Graph

from yang_to_rdf.input_handler import collect_yang_files, fetch_forge_release
from yang_to_rdf.namespace import DEFAULT_BASE_IRI, normalize_base_iri
from yang_to_rdf.output_writer import (
    bind_used_prefixes,
    module_prefix_map,
    module_stem,
    split_graph,
    stamp_versions,
    turtle_prefixes,
)
from yang_to_rdf.rdf_converter import YangToRDFConverter
from yang_to_rdf.reference_layer import ReferenceLayerBuilder
from yang_to_rdf.shacl_converter import YangToSHACLConverter
from yang_to_rdf.yang_parser import parse


def _build_layers(model, fmt: str, no_inference: bool) -> list[tuple[str, Graph]]:
    """Build the requested output layers once: [(layer_name, graph), ...].

    Shared by both --single-file and split output modes so the converters are
    invoked in exactly one place.
    """
    layers: list[tuple[str, Graph]] = []
    if fmt in ("rdf", "both"):
        layers.append(("rdf", YangToRDFConverter(model).convert()))
    if fmt in ("shacl", "both"):
        layers.append(("shacl", YangToSHACLConverter(model).convert()))
    if not no_inference:
        layers.append(("refs", ReferenceLayerBuilder(model).build()))
    return layers


def main():
    p = argparse.ArgumentParser(
        description="Convert a complete 3GPP YANG module set to RDF TBox + SHACL shapes",
        epilog="Example: yang-to-rdf MnS-Rel-19-yang-models.zip",
    )
    p.add_argument("input", nargs="*", help="Path(s) to .yang, directory, or .zip")
    p.add_argument("--format", choices=["rdf", "shacl", "both"], default="both")
    p.add_argument("--no-inference", action="store_true",
                   help="Skip the reference extension layer (<stem>_refs.ttl)")
    p.add_argument("--single-file", action="store_true",
                   help="Write one merged TTL per layer instead of one file per YANG module (default: split per module)")
    p.add_argument("--output", "-o", default="output")
    p.add_argument(
        "--base-iri", dest="base_iri", default=DEFAULT_BASE_IRI,
        help=(f"Base IRI for every emitted term (default: {DEFAULT_BASE_IRI}). "
              f"Must be an absolute http(s) IRI. The default names an "
              f"Ericsson-owned namespace minted by this project; it is not "
              f"currently dereferenceable and asserts no 3GPP endorsement."))
    p.add_argument("--release", default=None,
                   help="Release/version label (e.g. Rel-19, Tag_Rel20_SA112); recorded as owl:versionIRI / owl:versionInfo so multiple releases can be told apart. See VERSIONING.md.")
    p.add_argument("--fetch-release", dest="fetch_release", default=None,
                   help="Download yang-models for this ref from 3GPP forge (e.g. Rel-19, Tag_Rel20_SA112)")
    p.add_argument("--ref-type", choices=["heads", "tags"], default="heads",
                   help="Ref type for --fetch-release: heads (branch) or tags (tag)")
    p.add_argument("--version", action="version", version="%(prog)s 0.3.0")
    args = p.parse_args()

    try:
        args.base_iri = normalize_base_iri(args.base_iri)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle --fetch-release before input collection
    if args.fetch_release:
        print(f"Downloading 3GPP MnS yang-models for {args.fetch_release} ...")
        fetched_zip = fetch_forge_release(args.fetch_release, args.ref_type)
        args.input = [fetched_zip]
        # Default release label to the fetched ref if not explicitly set
        if not args.release:
            args.release = args.fetch_release

    if not args.input:
        print("Error: either provide input files/dirs or use --fetch-release", file=sys.stderr)
        sys.exit(1)

    try:
        yang_files, search_paths = collect_yang_files(args.input)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if not yang_files:
        print("No .yang files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(yang_files)} YANG files")
    model, errors = parse(yang_files, search_paths, base_iri=args.base_iri)
    if errors:
        print(f"WARNING: {len(errors)} validation error(s); output may be incomplete:",
              file=sys.stderr)
        for e in errors[:10]:
            print(f"  {e}", file=sys.stderr)
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more", file=sys.stderr)
    print(f"Parsed {len(model.iocs)} IOCs, {len(model.typedefs)} typedefs")

    os.makedirs(args.output, exist_ok=True)

    # Build every requested layer once; the two modes differ only in routing.
    layers = _build_layers(model, args.format, args.no_inference)

    if args.single_file:
        # One merged file per layer.
        stem = Path(args.input[0]).stem
        titles = {"rdf": "RDF TBox", "shacl": "SHACL shapes", "refs": "Reference layer"}
        prefixes = turtle_prefixes(model)
        for layer_name, g in layers:
            stamp_versions(g, model, release_label=args.release, aggregate=True)
            bind_used_prefixes(g, prefixes)
            path = os.path.join(args.output, f"{stem}_{layer_name}.ttl")
            g.serialize(destination=path, format="turtle")
            print(f"{titles[layer_name]} -> {path} ({len(g)} triples)")
    else:
        # One file per module per layer, plus a shared index.ttl.
        index = Graph()
        file_count = 0
        module_count = 0
        prefix_map = module_prefix_map(args.base_iri, model.module_iris)
        prefixes = turtle_prefixes(model)
        for layer_name, layer_graph in layers:
            mods, leftover = split_graph(layer_graph, prefix_map, args.base_iri)
            # Accumulate leftovers into shared index (carry prefixes for readable ttl)
            for prefix, ns in leftover.namespaces():
                index.bind(prefix, ns)
            for t in leftover:
                index.add(t)
            for module_iri_, mg in sorted(mods.items()):  # sorted → deterministic
                stamp_versions(mg, model)
                # Bind only this module's own + referenced prefixes: binding all
                # of them made conversion 10x slower. See bind_used_prefixes.
                bind_used_prefixes(mg, prefixes)
                stem = module_stem(module_iri_)
                path = os.path.join(args.output, f"{stem}_{layer_name}.ttl")
                mg.serialize(destination=path, format="turtle")
                file_count += 1
            module_count = max(module_count, len(mods))

        stamp_versions(index, model, release_label=args.release, aggregate=True)
        bind_used_prefixes(index, prefixes)
        index_path = os.path.join(args.output, "index.ttl")
        index.serialize(destination=index_path, format="turtle")
        file_count += 1
        print(f"Split output -> {args.output}/ ({module_count} modules, {file_count} files)")

    print("Done.")


if __name__ == "__main__":
    main()
