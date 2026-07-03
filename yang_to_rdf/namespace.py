"""IRI construction from YANG namespaces and schema paths.

Strategy:
- Module namespace (e.g. urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction) becomes the prefix base.
- Class IRI: <base>/ClassName
- Property IRI: <base>/ClassName/propertyName  (path-scoped, avoids multi-domain)
- Configurable base override replaces the URN with an HTTP namespace.
"""

from __future__ import annotations

from urllib.parse import quote


def module_base_iri(yang_namespace: str, base_override: str | None = None) -> str:
    """Derive the RDF namespace base IRI from a YANG module namespace.

    If base_override is provided, the module's local name is appended to it.
    E.g. base_override="https://3gpp.org/nrm/" + module "_3gpp-5gc-nrm-amffunction"
    → "https://3gpp.org/nrm/_3gpp-5gc-nrm-amffunction/"
    """
    # Extract local module name from URN (last segment after ':')
    local = yang_namespace.rsplit(":", 1)[-1] if ":" in yang_namespace else yang_namespace

    if base_override:
        base = base_override.rstrip("/")
        return f"{base}/{local}/"
    # Use the YANG namespace directly, appending / for path-based IRIs
    return f"{yang_namespace}/"


def class_iri(base: str, class_name: str) -> str:
    """Build IRI for a class (IOC)."""
    return f"{base}{quote(class_name, safe='')}"


def property_iri(base: str, class_name: str, prop_name: str) -> str:
    """Build path-scoped property IRI: <base>/ClassName/propName."""
    return f"{base}{quote(class_name, safe='')}/{quote(prop_name, safe='')}"
