import os, glob, zipfile, tempfile, shutil
from pathlib import Path
import pytest

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
