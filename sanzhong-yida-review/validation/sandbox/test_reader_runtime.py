"""Allowlisted dependency staging does not copy arbitrary site packages or hooks."""
import hashlib
import importlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

@pytest.fixture
def reader():
    try:
        return importlib.import_module("sandbox_reader_runtime")
    except ModuleNotFoundError:
        pytest.fail("sandbox_reader_runtime implementation missing")

def source(tmp_path):
    base = tmp_path / "python"
    site = base / "Lib" / "site-packages"
    site.mkdir(parents=True)
    return base, site

def test_only_fixed_packages_and_metadata_are_staged(reader, tmp_path):
    base, site = source(tmp_path)
    (site / "pypdf").mkdir(); (site / "pypdf" / "__init__.py").write_text("CANARY", encoding="utf8")
    (site / "pypdf-1.2.3.dist-info").mkdir()
    (site / "pypdf-1.2.3.dist-info" / "METADATA").write_text("Name: pypdf\nVersion: 1.2.3\n", encoding="utf8")
    (site / "typing_extensions.py").write_text("pass", encoding="utf8")
    (site / "openai").mkdir(); (site / "openai" / "auth.py").write_text("must not copy", encoding="utf8")
    (site / "unlisted-1.dist-info").mkdir()
    (site / "inject.pth").write_text("import unsafe", encoding="utf8")
    (site / "pypdf" / "hidden.pth").write_text("import unsafe", encoding="utf8")
    (site / "pypdf" / "__pycache__").mkdir(); (site / "pypdf" / "__pycache__" / "cached.pyc").write_bytes(b"cache")
    target = tmp_path / "target"
    manifest = reader.stage_reader_libraries(base, target)
    assert {path.name for path in target.iterdir()} == {"pypdf", "pypdf-1.2.3.dist-info", "typing_extensions.py"}
    assert not (target / "pypdf" / "hidden.pth").exists()
    assert not (target / "pypdf" / "__pycache__").exists()
    assert manifest["versions"]["pypdf"] == "1.2.3"
    entries = {entry["path"]: entry for entry in manifest["files"]}
    assert entries["pypdf/__init__.py"]["sha256"] == hashlib.sha256(b"CANARY").hexdigest()
    assert entries["pypdf/__init__.py"]["size"] == 6

def test_native_support_libraries_are_allowlisted(reader, tmp_path):
    base, site = source(tmp_path)
    for name in ("pypdfium2_raw", "pillow.libs", "lxml.libs"):
        (site / name).mkdir(); (site / name / "native.dll").write_bytes(b"fixture-only")
    target = tmp_path / "target"
    manifest = reader.stage_reader_libraries(base, target)
    assert set(manifest["copied_roots"]) == {"pypdfium2_raw", "pillow.libs", "lxml.libs"}
    assert len(manifest["files"]) == 3

def test_staging_refuses_existing_files_in_target(reader, tmp_path):
    base, site = source(tmp_path)
    target = tmp_path / "target"; target.mkdir(); (target / "existing.pth").write_text("unsafe", encoding="utf8")
    with pytest.raises(ValueError, match="empty"):
        reader.stage_reader_libraries(base, target)

def test_missing_source_is_reported_without_creating_a_runtime(reader, tmp_path):
    with pytest.raises(FileNotFoundError):
        reader.stage_reader_libraries(tmp_path / "missing", tmp_path / "target")
    assert not (tmp_path / "target").exists()


def test_pdfium_distribution_companion_is_fixed_allowlist_not_general_config(reader, tmp_path):
    base, site = source(tmp_path)
    (site / "pypdfium2_cfg").mkdir()
    (site / "pypdfium2_cfg" / "__init__.py").write_text("DEBUG_AUTOCLOSE = False", encoding="utf8")
    (site / "user_config").mkdir(); (site / "user_config" / "auth.json").write_text("do not copy", encoding="utf8")
    (site / "pypdfium2_cfg-1.0.dist-info").mkdir()
    (site / "pypdfium2_cfg-1.0.dist-info" / "METADATA").write_text("Name: pypdfium2-cfg\nVersion: 1.0\n", encoding="utf8")
    target = tmp_path / "target"
    manifest = reader.stage_reader_libraries(base, target)
    assert (target / "pypdfium2_cfg" / "__init__.py").is_file()
    assert not (target / "user_config").exists()
    assert manifest["versions"]["pypdfium2-cfg"] == "1.0"
