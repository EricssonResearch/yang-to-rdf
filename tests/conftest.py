import os
import glob
import zipfile
import tempfile
import shutil
from pathlib import Path
import pytest
from yang_to_rdf.pyang_context import build_context
from yang_to_rdf.yang_parser import parse

def _find_zip():
    env = os.environ.get("YANG_TEST_ZIP")
    if env and Path(env).is_file():
        return Path(env)
    cand = Path(__file__).resolve().parent.parent / "MnS-Rel-19-yang-models.zip"
    return cand if cand.is_file() else None

@pytest.fixture(scope="session")
def extracted_set():
    zp = _find_zip()
    if zp is None:
        pytest.skip("MnS-Rel-19-yang-models.zip not found (set YANG_TEST_ZIP)")
    d = tempfile.mkdtemp(prefix="yang_test_")
    with zipfile.ZipFile(zp) as zf:
        zf.extractall(d)
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture(scope="session")
def yang_dir(extracted_set):
    hits = glob.glob(os.path.join(extracted_set, "**", "_3gpp-common-managed-element.yang"), recursive=True)
    assert hits, "yang-models dir not found in zip"
    return str(Path(hits[0]).parent)

@pytest.fixture(scope="session")
def external_yams_dir(yang_dir):
    return str(Path(yang_dir) / "external-yams")

@pytest.fixture(scope="session")
def parsed_context(yang_dir, external_yams_dir):
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    return build_context(files, [yang_dir, external_yams_dir])

@pytest.fixture(scope="session")
def parsed_model(yang_dir, external_yams_dir):
    """Parse the full set ONCE per session (parsing is the slow step; the model is
    read-only in tests). Returns (model, errors)."""
    files = sorted(glob.glob(os.path.join(yang_dir, "_3gpp*.yang")))
    return parse(files, [yang_dir, external_yams_dir])


# A minimal self-contained module subset for CLI-behavior tests (file layout,
# split/single, --no-inference, determinism). These verify wiring, which is
# dataset-size-independent, so running the CLI subprocess against ~8 modules
# (~1s) instead of the full 120 (~15s) keeps the suite fast.
_TINY_MODULES = [
    "_3gpp-common-yang-types", "_3gpp-common-top", "_3gpp-common-yang-extensions",
    "_3gpp-common-managed-element", "_3gpp-common-managed-function",
    "_3gpp-5g-common-yang-types", "_3gpp-common-subnetwork",
    "_3gpp-5gc-nrm-ausffunction",
]

@pytest.fixture(scope="session")
def tiny_yang_dir(yang_dir):
    d = tempfile.mkdtemp(prefix="yang_tiny_")
    for name in _TINY_MODULES:
        src = os.path.join(yang_dir, name + ".yang")
        if os.path.isfile(src):
            shutil.copy(src, d)
    ext = os.path.join(yang_dir, "external-yams")
    if os.path.isdir(ext):
        shutil.copytree(ext, os.path.join(d, "external-yams"))
    yield d
    shutil.rmtree(d, ignore_errors=True)
