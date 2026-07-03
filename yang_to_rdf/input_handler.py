"""Handle input sources: zip files, directories, individual .yang files."""
from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

EXTERNAL_DIR_NAMES = {"external-yams", "external-yangs"}


def _is_external(path: Path) -> bool:
    return any(part in EXTERNAL_DIR_NAMES for part in path.parts)


def _augment_search_paths(root: Path, search_paths: list[str]) -> None:
    for name in EXTERNAL_DIR_NAMES:
        ext = root / name
        if ext.is_dir():
            search_paths.append(str(ext))


def collect_yang_files(input_paths: list[str]) -> tuple[list[str], list[str]]:
    """Collect .yang conversion targets and pyang search paths from inputs."""
    all_files: list[str] = []
    search_paths: list[str] = []

    for input_path in input_paths:
        path = Path(input_path)
        if path.is_file() and path.suffix == ".zip":
            files, sp = _extract_zip(path)
            all_files.extend(files)
            search_paths.append(sp)
            _augment_search_paths(Path(sp), search_paths)
            # nested external-deps folder inside zip (e.g. yang-models/external-yams/)
            for name in EXTERNAL_DIR_NAMES:
                for child in Path(sp).rglob(name):
                    if child.is_dir():
                        search_paths.append(str(child))
                        search_paths.append(str(child.parent))
        elif path.is_dir():
            yang_files = [
                str(f) for f in sorted(path.rglob("*.yang")) if not _is_external(f)
            ]
            all_files.extend(yang_files)
            search_paths.append(str(path))
            _augment_search_paths(path, search_paths)
        elif path.is_file() and path.suffix == ".yang":
            all_files.append(str(path))
            search_paths.append(str(path.parent))
        else:
            raise ValueError(
                f"Input must be a .yang file, directory, or .zip: {input_path}"
            )

    all_files = list(dict.fromkeys(all_files))
    search_paths = list(dict.fromkeys(search_paths))
    return all_files, search_paths


def _extract_zip(zip_path: Path) -> tuple[list[str], str]:
    """Extract .yang files from a zip to a temp dir, guarding against zip-slip."""
    extract_dir = Path(tempfile.mkdtemp(prefix="yang_to_rdf_"))
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if not member.endswith(".yang"):
                continue
            dest = (extract_dir / member).resolve()
            if not str(dest).startswith(str(extract_dir.resolve()) + os.sep):
                raise ValueError(f"Unsafe path in zip (zip-slip): {member}")
            zf.extract(member, extract_dir)

    yang_files = [
        str(f) for f in sorted(extract_dir.rglob("*.yang")) if not _is_external(f)
    ]
    return yang_files, str(extract_dir)
