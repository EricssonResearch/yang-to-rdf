"""CLI entry point for yang-to-rdf."""
import argparse
import os
import sys
from pathlib import Path

from yang_to_rdf.input_handler import collect_yang_files, fetch_forge_release
from yang_to_rdf.output_writer import module_stem, split_graph, stamp_versions
from yang_to_rdf.rdf_converter import YangToRDFConverter
from yang_to_rdf.reference_layer import ReferenceLayerBuilder
from yang_to_rdf.shacl_converter import YangToSHACLConverter
from yang_to_rdf.yang_parser import parse


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
    p.add_argument("--release", default=None,
                   help="Release/version label (e.g. Rel-19, Tag_Rel20_SA112); recorded as owl:versionIRI / owl:versionInfo so multiple releases can be told apart. See VERSIONING.md.")
    p.add_argument("--fetch-release", dest="fetch_release", default=None,
                   help="Download yang-models for this ref from 3GPP forge (e.g. Rel-19, Tag_Rel20_SA112)")
    p.add_argument("--ref-type", choices=["heads", "tags"], default="heads",
                   help="Ref type for --fetch-release: heads (branch) or tags (tag)")
    p.add_argument("--version", action="version", version="%(prog)s 0.2.0")
    args = p.parse_args()

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
    model, errors = parse(yang_files, search_paths)
    if errors:
        print(f"WARNING: {len(errors)} validation error(s); output may be incomplete:",
              file=sys.stderr)
        for e in errors[:10]:
            print(f"  {e}", file=sys.stderr)
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more", file=sys.stderr)
    print(f"Parsed {len(model.iocs)} IOCs, {len(model.typedefs)} typedefs")

    os.makedirs(args.output, exist_ok=True)

    if args.single_file:
        # Original behavior: one merged file per layer
        stem = Path(args.input[0]).stem

        if args.format in ("rdf", "both"):
            g = YangToRDFConverter(model).convert()
            stamp_versions(g, model, release_label=args.release, aggregate=True)
            path = os.path.join(args.output, f"{stem}_rdf.ttl")
            g.serialize(destination=path, format="turtle")
            print(f"RDF TBox -> {path} ({len(g)} triples)")

        if args.format in ("shacl", "both"):
            g = YangToSHACLConverter(model).convert()
            stamp_versions(g, model, release_label=args.release, aggregate=True)
            path = os.path.join(args.output, f"{stem}_shacl.ttl")
            g.serialize(destination=path, format="turtle")
            print(f"SHACL shapes -> {path} ({len(g)} triples)")

        if not args.no_inference:
            g = ReferenceLayerBuilder(model).build()
            stamp_versions(g, model, release_label=args.release, aggregate=True)
            path = os.path.join(args.output, f"{stem}_refs.ttl")
            g.serialize(destination=path, format="turtle")
            print(f"Reference layer -> {path} ({len(g)} triples)")
    else:
        # Split mode: one file per module per layer, plus shared index.ttl
        from rdflib import Graph
        index = Graph()
        file_count = 0
        module_count = 0

        layers = []
        if args.format in ("rdf", "both"):
            layers.append(("rdf", YangToRDFConverter(model).convert()))
        if args.format in ("shacl", "both"):
            layers.append(("shacl", YangToSHACLConverter(model).convert()))
        if not args.no_inference:
            layers.append(("refs", ReferenceLayerBuilder(model).build()))

        for layer_name, layer_graph in layers:
            mods, leftover = split_graph(layer_graph)
            # Accumulate leftovers into shared index (carry prefixes for readable ttl)
            for prefix, ns in leftover.namespaces():
                index.bind(prefix, ns)
            for t in leftover:
                index.add(t)

            # Write per-module files
            for urn, mg in mods.items():
                stamp_versions(mg, model)
                stem = module_stem(urn)
                path = os.path.join(args.output, f"{stem}_{layer_name}.ttl")
                mg.serialize(destination=path, format="turtle")
                file_count += 1

            if layer_name == "rdf":  # Count modules once
                module_count = len(mods)

        # Stamp index with aggregate versionIRI
        stamp_versions(index, model, release_label=args.release, aggregate=True)

        # Write shared index.ttl
        index_path = os.path.join(args.output, "index.ttl")
        index.serialize(destination=index_path, format="turtle")
        file_count += 1

        print(f"Split output -> {args.output}/ ({module_count} modules, {file_count} files)")

    print("Done.")


if __name__ == "__main__":
    main()
