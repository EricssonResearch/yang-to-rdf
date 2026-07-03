"""Shared resolution of YANG types over the resolved typedef chain."""
from __future__ import annotations

from dataclasses import dataclass, field

from rdflib import URIRef
from rdflib.namespace import XSD

DN_TYPEDEFS = {"DistinguishedName", "Dn", "LDN"}

YANG_TO_XSD = {
    "string": XSD.string, "boolean": XSD.boolean,
    "uint8": XSD.unsignedByte, "uint16": XSD.unsignedShort,
    "uint32": XSD.unsignedInt, "uint64": XSD.unsignedLong,
    "int8": XSD.byte, "int16": XSD.short, "int32": XSD.int, "int64": XSD.long,
    "decimal64": XSD.decimal, "empty": XSD.boolean, "binary": XSD.base64Binary,
    "instance-identifier": XSD.anyURI, "union": XSD.string,
}
IETF_TYPE_MAP = {
    "inet:ipv4-address": XSD.string, "inet:ipv6-address": XSD.string,
    "inet:domain-name": XSD.string, "inet:host": XSD.string,
    "inet:host-name": XSD.string, "inet:uri": XSD.anyURI,
    "yang:date-and-time": XSD.dateTime, "yang:hex-string": XSD.string,
    "yang:counter64": XSD.unsignedLong, "yang:gauge64": XSD.unsignedLong,
}


@dataclass
class ResolvedType:
    xsd: URIRef | None = None
    enums: list[str] = field(default_factory=list)
    pattern: str | None = None
    is_reference: bool = False
    datatype_iri: str | None = None
    base_name: str = "string"


def _local(name: str) -> str:
    return name.split(":")[-1] if ":" in name else name


def resolve_type(type_stmt) -> ResolvedType:
    """Walk a leaf's type: follow the typedef chain, collect constraints."""
    rt = ResolvedType()
    if type_stmt is None:
        rt.xsd = XSD.string
        return rt

    # Walk the chain of type statements (leaf -> typedef -> typedef -> builtin).
    chain_names: list[str] = []
    cur = type_stmt
    for _ in range(12):
        chain_names.append(cur.arg)
        # collect enums/pattern from whichever level declares them
        for enum in cur.search("enum"):
            if enum.arg not in rt.enums:
                rt.enums.append(enum.arg)
        pat = cur.search_one("pattern")
        if pat is not None and rt.pattern is None:
            rt.pattern = pat.arg
        td = getattr(cur, "i_typedef", None)
        if td is None:
            break
        nxt = td.search_one("type")
        if nxt is None:
            break
        cur = nxt

    rt.base_name = cur.arg
    if any(_local(n) in DN_TYPEDEFS for n in chain_names):
        rt.is_reference = True

    # Map the base builtin/known type to XSD.
    base = cur.arg
    if base in YANG_TO_XSD:
        rt.xsd = YANG_TO_XSD[base]
    elif base in IETF_TYPE_MAP:
        rt.xsd = IETF_TYPE_MAP[base]
    elif base == "enumeration":
        rt.xsd = XSD.string
    else:
        rt.xsd = XSD.string
    return rt
