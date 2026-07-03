"""CLI entry point for yang-to-rdf."""

import argparse
import os
import sys
from pathlib import Path

from yang_to_rdf.input_handler import collect_yang_files
from yang_to_rdf.rdf_converter import YangToRDFConverter
from yang_to_rdf.shacl_converter import YangToSHACLConverter
from yang_to_rdf.yang_parser import parse_yang_files


def main():
    parser = argparse.ArgumentParser(
        description="Convert YANG modules to RDF TBox vocabularies and SHACL shapes",
        epilog="""
Examples:
  yang-to-rdf 28541-k20.zip
  yang-to-rdf /path/to/yang/modules/
  yang-to-rdf module.yang --base-namespace https://3gpp.org/nrm/
        """,
    )
    parser.add_argument(
        "input",
        nargs="+",
        help="Path(s) to .yang file(s), directory(ies), or .zip file(s)",
    )
    parser.add_argument(
        "--base-namespace",
        default=None,
        help="Base namespace override for generated IRIs (default: use YANG namespace URNs)",
    )
    parser.add_argument(
        "--format",
        choices=["rdf", "shacl", "both"],
        default="both",
        help="Output format (default: both)",
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="Output directory (default: output/)",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    args = parser.parse_args()

    # Collect YANG files
    try:
        yang_files, search_paths = collect_yang_files(args.input)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not yang_files:
        print("No .yang files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(yang_files)} YANG files")

    # Parse
    print("Parsing YANG modules...")
    modules, submodule_groupings = parse_yang_files(yang_files, search_paths)
    print(f"Parsed {len(modules)} modules ({len(submodule_groupings)} submodule groupings)")

    if not modules:
        print("No modules parsed successfully.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    # Derive output prefix from first input name
    input_stem = Path(args.input[0]).stem

    # Convert
    if args.format in ("rdf", "both"):
        print("Generating RDF TBox...")
        rdf_conv = YangToRDFConverter(
            modules, base_namespace=args.base_namespace,
            submodule_groupings=submodule_groupings,
        )
        graph = rdf_conv.convert()
        rdf_path = os.path.join(args.output, f"{input_stem}_rdf.ttl")
        graph.serialize(destination=rdf_path, format="turtle")
        print(f"✓ RDF TBox written to {rdf_path} ({len(graph)} triples)")

    if args.format in ("shacl", "both"):
        print("Generating SHACL shapes...")
        shacl_conv = YangToSHACLConverter(
            modules, base_namespace=args.base_namespace,
            submodule_groupings=submodule_groupings,
        )
        graph = shacl_conv.convert()
        shacl_path = os.path.join(args.output, f"{input_stem}_shacl.ttl")
        graph.serialize(destination=shacl_path, format="turtle")
        print(f"✓ SHACL shapes written to {shacl_path} ({len(graph)} triples)")

    print("Done.")


if __name__ == "__main__":
    main()
