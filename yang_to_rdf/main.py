"""CLI entry point for yang-to-rdf."""
import argparse
import os
import sys
from pathlib import Path

from yang_to_rdf.input_handler import collect_yang_files
from yang_to_rdf.rdf_converter import YangToRDFConverter
from yang_to_rdf.reference_layer import ReferenceLayerBuilder
from yang_to_rdf.shacl_converter import YangToSHACLConverter
from yang_to_rdf.yang_parser import parse


def main():
    p = argparse.ArgumentParser(
        description="Convert a complete 3GPP YANG module set to RDF TBox + SHACL shapes",
        epilog="Example: yang-to-rdf MnS-Rel-19-yang-models.zip",
    )
    p.add_argument("input", nargs="+", help="Path(s) to .yang, directory, or .zip")
    p.add_argument("--format", choices=["rdf", "shacl", "both"], default="both")
    p.add_argument("--no-inference", action="store_true",
                   help="Skip the reference extension layer (<stem>_refs.ttl)")
    p.add_argument("--output", "-o", default="output")
    p.add_argument("--version", action="version", version="%(prog)s 0.2.0")
    args = p.parse_args()

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
    stem = Path(args.input[0]).stem

    if args.format in ("rdf", "both"):
        g = YangToRDFConverter(model).convert()
        path = os.path.join(args.output, f"{stem}_rdf.ttl")
        g.serialize(destination=path, format="turtle")
        print(f"RDF TBox -> {path} ({len(g)} triples)")

    if args.format in ("shacl", "both"):
        g = YangToSHACLConverter(model).convert()
        path = os.path.join(args.output, f"{stem}_shacl.ttl")
        g.serialize(destination=path, format="turtle")
        print(f"SHACL shapes -> {path} ({len(g)} triples)")

    if not args.no_inference:
        g = ReferenceLayerBuilder(model).build()
        path = os.path.join(args.output, f"{stem}_refs.ttl")
        g.serialize(destination=path, format="turtle")
        print(f"Reference layer -> {path} ({len(g)} triples)")

    print("Done.")


if __name__ == "__main__":
    main()
