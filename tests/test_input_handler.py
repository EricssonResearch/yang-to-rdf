# tests/test_input_handler.py
import os, zipfile
import pytest
from yang_to_rdf.input_handler import collect_yang_files, _extract_zip

def test_external_yams_added_to_search_path(tmp_path):
    root = tmp_path / "set"
    (root / "external-yams").mkdir(parents=True)
    (root / "a.yang").write_text("module a {}")
    (root / "external-yams" / "dep.yang").write_text("module dep {}")
    files, paths = collect_yang_files([str(root)])
    assert any(p.endswith("external-yams") for p in paths)
    # dependency module is NOT a conversion target
    assert not any(f.endswith("dep.yang") for f in files)
    assert any(f.endswith("a.yang") for f in files)

def test_zip_slip_rejected(tmp_path):
    bad = tmp_path / "evil.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../escape.yang", "module x {}")
    with pytest.raises(ValueError):
        _extract_zip(bad)
