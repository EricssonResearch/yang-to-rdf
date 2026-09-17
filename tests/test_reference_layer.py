# tests/test_reference_layer.py
import re
from collections import Counter

from rdflib import RDFS, Literal, URIRef

from tests._shared import (
    Y2R,
    cached_parse,
    cached_refs_graph as _graph,
    prop_iri,
)


def test_unambiguous_range_inferred(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    ref = URIRef(prop_iri("_3gpp-5gc-nrm-amffunction", "AMFFunction", "aMFSetRef"))
    ranges = [str(r) for r in g.objects(ref, RDFS.range)]
    assert any(r.endswith("#AMFSet") for r in ranges), ranges
    assert (ref, Y2R.confidence, Literal("unambiguous")) in g


def test_unresolved_ref_listed_not_dropped(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    subj = [s for s in g.subjects(Y2R.confidence, Literal("unresolved"))
            if str(s).endswith("_5GCNFRef")]
    assert subj, "unresolved DN ref must be recorded, not silently dropped"
    assert list(g.objects(subj[0], RDFS.range)) == []


def test_ambiguous_candidate_not_marked_unambiguous(yang_dir, external_yams_dir):
    # A candidate name shared by multiple IOCs across modules must NOT be
    # labeled unambiguous, even though a name match exists.
    model, _ = cached_parse(yang_dir, external_yams_dir)
    ioc_names = Counter(c.name for c in model.classes if c.kind == "ioc")
    g = _graph(yang_dir, external_yams_dir)
    suffix = re.compile(r"(RefList|Refs|Ref|List)$")
    marked = list(g.subjects(Y2R.confidence, Literal("unambiguous")))
    assert marked, "no properties marked unambiguous -- the check could not run"
    for prop in marked:
        # A property local name is "<Class>.<leaf>"; take the leaf half.
        leaf = str(prop).rsplit("#", 1)[-1].rsplit(".", 1)[-1]
        stub = suffix.sub("", leaf)
        cand = stub[0].upper() + stub[1:] if stub else stub
        assert ioc_names[cand] == 1, (
            f"{leaf} marked unambiguous but candidate {cand} has "
            f"{ioc_names[cand]} IOCs")
