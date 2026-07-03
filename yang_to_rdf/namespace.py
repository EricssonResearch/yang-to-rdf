"""IRI construction from YANG namespaces and schema paths.

Strategy:
- Module namespace (e.g. urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction) becomes the prefix base.
- Class IRI: <base>/ClassName
- Property IRI: <base>/ClassName/propertyName  (path-scoped, avoids multi-domain)
- Configurable base override replaces the URN with an HTTP namespace.
"""

from __future__ import annotations

from urllib.parse import quote


def class_iri(base: str, class_name: str) -> str:
    """Build IRI for a class (IOC)."""
    return f"{base}{quote(class_name, safe='')}"


def property_iri(base: str, class_name: str, prop_name: str) -> str:
    """Build path-scoped property IRI: <base>/ClassName/propName."""
    return f"{base}{quote(class_name, safe='')}/{quote(prop_name, safe='')}"
