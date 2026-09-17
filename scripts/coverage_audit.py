#!/usr/bin/env python3
"""Coverage audit: does the emitted RDF/SHACL represent what the parser found?

Full YANG<->RDF round-trip equivalence is intentionally NOT a goal — the
conversion is a documented, lossy projection (see CONVERSION_NOTES.md §6: choice
mutual-exclusivity, exact type facets, and DN targets are deliberately dropped).
So "do they represent the same things?" is audited as **coverage + parity**, not
round-trip identity:

  1. Parser completeness — the parser surfaces any attribute node *kind* it did
     not model (via the `unmodeled attribute node kind` warnings). Zero means no
     schema construct was silently skipped.
  2. RDF coverage — every class, leaf, and structured-attribute link in the IR
     appears as a triple in the RDF TBox. Catches converter drops.
  3. RDF/SHACL parity — every emitted class has a SHACL NodeShape (and vice
     versa). Catches the two converters diverging (a real past bug).

This is a projection audit, not proof of semantic equivalence; instance-level
equivalence (validate the same data against YANG and against the SHACL) is a
stronger, separate check that needs sample data + pyshacl/yangson.

Usage:
    python scripts/coverage_audit.py <input.zip|dir> [--search PATH ...]

Exits non-zero if any coverage gap is found.
"""
from __future__ import annotations

import argparse
import sys

from rdflib import RDF, RDFS, URIRef

from yang_to_rdf.input_handler import collect_yang_files
from yang_to_rdf.namespace import (
    class_iri,
    namespace_base,
    property_iri,
    vocab_namespace,
)
from yang_to_rdf.rdf_converter import YangToRDFConverter
from yang_to_rdf.shacl_converter import SH, YangToSHACLConverter
from yang_to_rdf.yang_parser import parse


def audit(model, rdf, shacl) -> dict:
    """Return a report dict of coverage gaps (empty lists == fully covered)."""
    rdf_missing_class: list[str] = []
    rdf_missing_leaf: list[str] = []
    rdf_missing_attr: list[str] = []

    for cls in model.classes:
        base = namespace_base(cls.namespace)
        cls_uri = URIRef(class_iri(base, cls.name))
        if (cls_uri, RDF.type, RDFS.Class) not in rdf:
            rdf_missing_class.append(str(cls_uri))
        for leaf in cls.leaves:
            prop = URIRef(property_iri(base, cls.name, leaf.name))
            if (prop, RDFS.domain, cls_uri) not in rdf:
                rdf_missing_leaf.append(str(prop))
        for ref in cls.attr_refs:
            prop = URIRef(property_iri(base, cls.name, ref.name))
            if (prop, RDFS.domain, cls_uri) not in rdf:
                rdf_missing_attr.append(str(prop))

    # RDF/SHACL class parity (ManagedFunction is a vocab base class, no shape).
    rdf_classes = {str(s) for s in rdf.subjects(RDF.type, RDFS.Class)}
    rdf_classes.discard(str(vocab_namespace(model.base_iri).ManagedFunction))
    shape_targets = {str(o) for o in shacl.objects(None, SH.targetClass)}
    class_no_shape = sorted(rdf_classes - shape_targets)
    shape_no_class = sorted(shape_targets - rdf_classes)

    return {
        "rdf_missing_class": rdf_missing_class,
        "rdf_missing_leaf": rdf_missing_leaf,
        "rdf_missing_attr": rdf_missing_attr,
        "class_without_shape": class_no_shape,
        "shape_without_class": shape_no_class,
    }


def run(inputs: list[str]) -> int:
    yang_files, search_paths = collect_yang_files(inputs)
    model, errors = parse(yang_files, search_paths)

    unmodeled = [e for e in errors if "unmodeled attribute node kind" in e]
    rdf = YangToRDFConverter(model).convert()
    shacl = YangToSHACLConverter(model).convert()
    report = audit(model, rdf, shacl)

    n_leaves = sum(len(c.leaves) for c in model.classes)
    n_attrs = sum(len(c.attr_refs) for c in model.classes)
    print(f"Parsed: {len(model.classes)} classes, {n_leaves} leaves, "
          f"{n_attrs} structured-attribute links, {len(model.typedefs)} typedefs")

    gaps = 0
    if unmodeled:
        gaps += len(unmodeled)
        print(f"\n[1] Parser completeness: {len(unmodeled)} UNMODELED node kind(s):")
        for u in unmodeled:
            print(f"    - {u}")
    else:
        print("[1] Parser completeness: OK (no unmodeled attribute node kinds)")

    rdf_gaps = (report["rdf_missing_class"] + report["rdf_missing_leaf"]
                + report["rdf_missing_attr"])
    if rdf_gaps:
        gaps += len(rdf_gaps)
        print(f"\n[2] RDF coverage: {len(rdf_gaps)} IR element(s) missing from RDF:")
        for x in rdf_gaps[:20]:
            print(f"    - {x}")
    else:
        print("[2] RDF coverage: OK (every IR class/leaf/attr present in RDF)")

    parity = report["class_without_shape"] + report["shape_without_class"]
    if parity:
        gaps += len(parity)
        print(f"\n[3] RDF/SHACL parity: {len(parity)} mismatch(es):")
        for x in parity[:20]:
            print(f"    - {x}")
    else:
        print("[3] RDF/SHACL parity: OK (every class has a shape and vice versa)")

    print(f"\n{'FAIL' if gaps else 'PASS'}: {gaps} coverage gap(s).")
    return 1 if gaps else 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", nargs="+", help="Path(s) to .yang, directory, or .zip")
    args = p.parse_args()
    sys.exit(run(args.input))


if __name__ == "__main__":
    main()
