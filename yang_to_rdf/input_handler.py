"""Handle input sources: zip files, directories, individual .yang files."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path


def collect_yang_files(input_paths: list[str]) -> tuple[list[str], list[str]]:
    """Collect .yang file paths from multiple inputs (zips, directories, files).

    Returns (list_of_yang_paths, search_paths_for_pyang).
    """
    all_files = []
    search_paths = []

    for input_path in input_paths:
        path = Path(input_path)
        if path.is_file() and path.suffix == ".zip":
            files, sp = _extract_zip(path)
            all_files.extend(files)
            search_paths.append(sp)
        elif path.is_dir():
            yang_files = sorted(str(f) for f in path.rglob("*.yang"))
            all_files.extend(yang_files)
            search_paths.append(str(path))
        elif path.is_file() and path.suffix == ".yang":
            all_files.append(str(path))
            search_paths.append(str(path.parent))
        else:
            raise ValueError(f"Input must be a .yang file, directory, or .zip: {input_path}")

    # Deduplicate
    all_files = list(dict.fromkeys(all_files))
    search_paths = list(dict.fromkeys(search_paths))
    return all_files, search_paths


def _extract_zip(zip_path: Path) -> tuple[list[str], str]:
    """Extract .yang files from a zip to a temp directory."""
    extract_dir = tempfile.mkdtemp(prefix="yang_to_rdf_")
    with zipfile.ZipFile(zip_path, "r") as zf:
        yang_members = [m for m in zf.namelist() if m.endswith(".yang")]
        for member in yang_members:
            zf.extract(member, extract_dir)

    yang_files = sorted(str(f) for f in Path(extract_dir).rglob("*.yang"))
    return yang_files, extract_dir
