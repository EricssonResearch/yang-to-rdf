"""Provenance header for generated artifacts, and the identity behind it.

ONE definition, because the header is emitted for every output file from a single
writer today but the contact and project URL are the kind of thing that gets copied
into a second place and then drifts when one is updated.

Added 2026-09-24, adapted from the sibling `openapi-to-rdf` project. Before this,
the generated `.ttl` files carried no provenance at all -- they opened straight into
`@prefix` lines. Nothing misattributed them, but nothing attributed them either: a
reader holding `_3gpp-5gc-nrm-amffunction_rdf.ttl` could not tell it was
machine-generated, from which module, or that the `rdfs:comment` text in it is the
source YANG's own prose rather than this project's.

The disclaimer sentence is the load-bearing one. A derived vocabulary that looks
official is worse than one that looks unfinished, because a reader may cite it as
the standard's own model of their network.
"""

from __future__ import annotations

#: Who to contact about a generated artifact. Not a copyright claim -- see NOTICE
#: for the rights in the source documents these artifacts are derived from.
CONTACT = "Jean Martins <jean.martins@ericsson.com>"

PROJECT_URL = "https://github.com/EricssonResearch/yang-to-rdf"

#: Human labels for the three output layers, used in the header's first line.
LAYER_TITLES = {
    "rdf": "RDF vocabulary (RDFS/OWL TBox)",
    "shacl": "SHACL validation shapes",
    "refs": "Reference-inference layer (heuristic; see CONVERSION_NOTES.md §3)",
    "index": "Aggregating ontology index",
}


def provenance_header(layer: str, source: str, regenerate: str) -> str:
    """A `#` comment block stating where a generated file came from.

    Args:
        layer: one of LAYER_TITLES, naming which output layer this file is.
        source: what it was converted FROM -- a YANG module name, or the upstream
            ref when the whole set was fetched. Never a local absolute path, which
            would leak the generating machine's filesystem into published output.
        regenerate: the exact command that reproduces this file.

    Deliberately GENERIC about the publisher. This converter runs on 3GPP YANG, on
    IETF modules and on arbitrary YANG, so naming a standards body in the header
    would be wrong for most inputs. Attribution for specific corpora belongs in
    NOTICE, which is a repository-level fact rather than a per-file one.

    Emitted as Turtle comments, so it must not change the parsed graph --
    `tests/test_provenance_header.py` asserts exactly that.
    """
    title = LAYER_TITLES.get(layer, layer)
    return (
        "# GENERATED FILE -- do not edit; your changes will be overwritten.\n"
        "#\n"
        f"# {title} produced by yang-to-rdf\n"
        f"#   {PROJECT_URL}\n"
        f"# Contact: {CONTACT}\n"
        f"# Source: {source}\n"
        "#\n"
        "# The CONVERSION is this project's work. The class and property names below,\n"
        "# and the `rdfs:comment` / `dcterms:description` text, are the source YANG's\n"
        "# own wording. The publisher of those modules did not produce, review or\n"
        "# endorse this file, and it must not be cited as their model. The IRI scheme,\n"
        "# the modelling decisions and the SHACL constraints are ours -- see\n"
        "# CONVERSION_NOTES.md. See NOTICE for the source documents and their terms.\n"
        "#\n"
        f"# Regenerate: {regenerate}\n"
        "\n"
    )


def source_label(fetch_release: str | None, ref_type: str | None,
                 module: str | None = None) -> str:
    """What to name as the source, without leaking a local path.

    When the set was fetched, the upstream ref identifies it reproducibly. When a
    local file or directory was supplied, say so WITHOUT the path: the path is
    specific to the generating machine and tells a reader nothing they can act on.
    """
    if fetch_release:
        origin = f"3GPP SA5 MnS forge, {ref_type or 'heads'} ref {fetch_release}"
    else:
        origin = "a locally supplied YANG module set"
    return f"{module} (from {origin})" if module else origin


def regenerate_command(fetch_release: str | None, ref_type: str | None) -> str:
    """The command that reproduces the file, as a reader could run it.

    Deliberately takes NO output directory. The first version interpolated the real
    one, which embedded `/tmp/y2r-verify-xxxx/converted` into freshly generated
    files while the committed examples said `examples/MnS-Rel-19-yang-models` -- so
    the container's byte-for-byte stage would have failed on every run, for a
    reason that has nothing to do with the vocabulary. The same objection as
    source_label's: a path from the generating machine is not reproducible and
    tells a reader nothing they can act on.
    """
    if fetch_release:
        return (f"uv run yang-to-rdf --fetch-release {fetch_release} "
                f"--ref-type {ref_type or 'heads'} -o <output-dir>")
    return "uv run yang-to-rdf <yang-module-set> -o <output-dir>"
