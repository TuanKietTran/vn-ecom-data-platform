import hashlib
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "scripts" / "export-ui-board.py"


def tiny_png() -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">II5B", 2, 3, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00\x00\x00" * 3))
        + chunk(b"IEND", b"")
    )


def manifest_for(path: Path, *, states: list | None = None) -> dict:
    image = path / "screen.png"
    image.write_bytes(tiny_png())
    source = path / "view.tsx"
    source.write_text("real source fingerprint", encoding="utf-8")
    return {
        "schema_version": 1,
        "worktree_revision": "abc123",
        "dirty": True,
        "build_id": "local-build-1",
        "captured_at_utc": "2026-10-29T00:00:00Z",
        "states": states
        if states is not None
        else [
            {
                "id": "web-home",
                "platform": "web",
                "route": "/",
                "viewport": {"width": 390, "height": 844},
                "png": "screen.png",
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "size_bytes": image.stat().st_size,
                "pixel_dimensions": [2, 3],
                "captured_at_utc": "2026-10-29T00:00:00Z",
                "source_files": [
                    {"path": "view.tsx", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
                ],
            }
        ],
        "transitions": [],
        "coverage": {"web": {"status": "CAPTURED"}},
    }


def export(tmp_path: Path, manifest: dict) -> subprocess.CompletedProcess:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(EXPORTER), str(manifest_path), str(tmp_path / "board.html")],
        capture_output=True,
        text=True,
    )


def test_exports_real_web_capture_and_marks_native_unverified(tmp_path: Path) -> None:
    result = export(tmp_path, manifest_for(tmp_path))
    assert result.returncode == 0, result.stderr
    page = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert "web-home" in page and "NOT CAPTURED/UNVERIFIED" in page
    assert "no Android SDK/emulator" in page and "no Xcode" in page
    assert "Original capture web-home" in page
    assert "No captured frames" in page
    assert page.count('<article class="frame"') == 1


def test_missing_capture_png_fails_closed(tmp_path: Path) -> None:
    manifest = manifest_for(tmp_path)
    (tmp_path / "screen.png").unlink()
    result = export(tmp_path, manifest)
    assert result.returncode == 1
    assert "missing PNG" in result.stderr
    assert not (tmp_path / "board.html").exists()


def test_mismatched_capture_checksum_fails_closed(tmp_path: Path) -> None:
    manifest = manifest_for(tmp_path)
    manifest["states"][0]["sha256"] = "0" * 64
    result = export(tmp_path, manifest)
    assert result.returncode == 1
    assert "SHA256 mismatch" in result.stderr
    assert not (tmp_path / "board.html").exists()


def test_empty_manifest_never_fabricates_native_frames(tmp_path: Path) -> None:
    manifest = manifest_for(tmp_path, states=[])
    result = export(tmp_path, manifest)
    assert result.returncode == 0, result.stderr
    page = (tmp_path / "board.html").read_text(encoding="utf-8")
    assert '<article class="frame"' not in page
    assert page.count("No captured frames.") == 3
