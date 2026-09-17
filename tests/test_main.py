import subprocess
import sys
from pathlib import Path

def test_cli_emits_three_layers_and_is_deterministic(tiny_yang_dir, tmp_path):
    out1 = tmp_path / "o1"
    out2 = tmp_path / "o2"
    cmd = [sys.executable, "-m", "yang_to_rdf.main", tiny_yang_dir, "-o"]
    subprocess.run(cmd + [str(out1), "--single-file"], check=True)
    subprocess.run(cmd + [str(out2), "--single-file"], check=True)
    stem = Path(tiny_yang_dir).name
    for suffix in ("_rdf.ttl", "_shacl.ttl", "_refs.ttl"):
        f1 = out1 / f"{stem}{suffix}"
        assert f1.is_file(), f"missing {suffix}"
        # deterministic across runs
        assert f1.read_bytes() == (out2 / f"{stem}{suffix}").read_bytes()

def test_no_inference_skips_refs(tiny_yang_dir, tmp_path):
    out = tmp_path / "o"
    subprocess.run(
        [sys.executable, "-m", "yang_to_rdf.main", tiny_yang_dir, "-o", str(out),
         "--no-inference", "--single-file"], check=True)
    stem = Path(tiny_yang_dir).name
    assert not (out / f"{stem}_refs.ttl").exists()
