"""Stage a fixed, credential-free document-reader dependency set for a role.

This host-side copier never imports the staged libraries, runs package hooks,
copies arbitrary site-packages, or changes ACLs. The launcher applies the role's
AppContainer ACL after staging and records the returned content manifest.
"""
from __future__ import annotations

from email.parser import Parser
import hashlib
import os
from pathlib import Path
import re
import shutil


READER_ROOTS = (
    "pypdf", "pypdfium2", "pypdfium2_raw", "pypdfium2_cfg", "openpyxl", "et_xmlfile", "docx", "pptx",
    "lxml", "PIL", "typing_extensions.py", "xlsxwriter", "pillow.libs", "lxml.libs",
)
METADATA_PREFIXES = (
    "pypdf", "pypdfium2", "pypdfium2_cfg", "openpyxl", "et_xmlfile", "python_docx", "python_pptx",
    "lxml", "pillow", "typing_extensions", "xlsxwriter",
)


def _plain(path: Path):
    stat = path.lstat()
    if path.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
        raise ValueError("reader runtime cannot contain links or reparse points: " + str(path))


def _eligible(path: Path):
    return path.name != "__pycache__" and path.suffix.lower() not in (".pth", ".pyc", ".pyo")


def _copy(source: Path, destination: Path):
    _plain(source)
    if not _eligible(source):
        return
    if source.is_dir():
        destination.mkdir()
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            _copy(child, destination / child.name)
    elif source.is_file():
        shutil.copyfile(source, destination)
    else:
        raise ValueError("reader runtime contains a non-regular file: " + str(source))


def stage_reader_libraries(base_python: Path, target_site_packages: Path) -> dict:
    """Copy present allowlisted readers into a new or empty target; return hashes.

    ``base_python`` is the directory containing the trusted bundled python.exe.
    Missing optional roots are reported. No fallback to another interpreter's
    libraries, user configuration, credentials, package manager, or network runs.
    """
    source = Path(base_python) / "Lib" / "site-packages"
    target = Path(target_site_packages)
    if not source.is_dir():
        raise FileNotFoundError("trusted Python site-packages missing: " + str(source))
    _plain(source)
    if target.exists():
        _plain(target)
        if not target.is_dir() or any(target.iterdir()):
            raise ValueError("reader runtime target must be a new or empty directory")
    else:
        target.mkdir(parents=True)
    candidates = [source / name for name in READER_ROOTS if (source / name).exists()]
    metadata_pattern = re.compile(r"^(?:" + "|".join(re.escape(name) for name in METADATA_PREFIXES) + r")-[0-9][^/\\]*\.dist-info$", re.IGNORECASE)
    metadata = sorted((entry for entry in source.iterdir() if metadata_pattern.fullmatch(entry.name)), key=lambda item: item.name)
    candidates.extend(metadata)
    versions = {}
    for directory in metadata:
        _plain(directory)
        metadata_file = directory / "METADATA"
        if metadata_file.is_file():
            _plain(metadata_file)
            fields = Parser().parsestr(metadata_file.read_text(encoding="utf8"))
            if fields.get("Name") and fields.get("Version"):
                versions[fields["Name"].lower().replace("_", "-")] = fields["Version"]
    for candidate in candidates:
        _copy(candidate, target / candidate.name)
    files = []
    for directory, folders, names in os.walk(target):
        folders.sort()
        for name in sorted(names):
            path = Path(directory) / name
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            files.append({"path": path.relative_to(target).as_posix(), "size": path.stat().st_size, "sha256": digest.hexdigest()})
    return {"schema": "sanzhong.reader-runtime.v1", "source_site_packages": str(source), "target_site_packages": str(target),
            "copied_roots": [candidate.name for candidate in candidates], "versions": versions,
            "missing_optional_roots": [name for name in READER_ROOTS if not (source / name).exists()],
            "files": files, "file_count": len(files), "total_bytes": sum(entry["size"] for entry in files)}
