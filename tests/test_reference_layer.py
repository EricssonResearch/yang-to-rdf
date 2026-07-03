# tests/test_reference_layer.py
import glob, os
from rdflib import RDFS, URIRef, Literal
from yang_to_rdf.yang_parser import parse
from yang_to_rdf.reference_layer import ReferenceLayerBuilder
from yang_to_rdf.rdf_converter import NRM

def _graph(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    model, _ = parse(files, [yang_dir, external_yams_dir])
    return ReferenceLayerBuilder(model).build()

def test_unambiguous_range_inferred(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    ref = URIRef("urn:3gpp:sa5:_3gpp-5gc-nrm-amffunction/AMFFunction/aMFSetRef")
    ranges = list(g.objects(ref, RDFS.range))
    assert any(str(r).endswith("/AMFSet") for r in ranges)
    assert (ref, NRM.confidence, Literal("unambiguous")) in g

def test_unresolved_ref_listed_not_dropped(yang_dir, external_yams_dir):
    g = _graph(yang_dir, external_yams_dir)
    subj = [s for s in g.subjects(NRM.confidence, Literal("unresolved"))
            if str(s).endswith("_5GCNFRef")]
    assert subj, "unresolved DN ref must be recorded, not silently dropped"
    assert list(g.objects(subj[0], RDFS.range)) == []
