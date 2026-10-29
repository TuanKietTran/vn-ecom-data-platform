#!/usr/bin/env python3
"""Export a checksum-verified, Figma-like board from real application captures."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

NATIVE_BLOCKERS = {
    "android": "no Android SDK/emulator; unavailable old runtime captures",
    "ios": "no Xcode; unavailable old runtime captures",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"not a PNG: {path}")
        width = height = None
        seen_end = False
        while chunk_header := stream.read(8):
            if len(chunk_header) != 8:
                raise ValueError(f"truncated PNG chunk: {path}")
            length, kind = struct.unpack(">I4s", chunk_header)
            payload = stream.read(length)
            crc_bytes = stream.read(4)
            if len(payload) != length or len(crc_bytes) != 4:
                raise ValueError(f"truncated PNG chunk: {path}")
            expected_crc = struct.unpack(">I", crc_bytes)[0]
            if zlib.crc32(kind + payload) & 0xFFFFFFFF != expected_crc:
                raise ValueError(f"PNG chunk CRC mismatch: {path}")
            if kind == b"IHDR":
                if width is not None or length != 13:
                    raise ValueError(f"invalid PNG IHDR: {path}")
                width, height = struct.unpack(">II", payload[:8])
            elif kind == b"IEND":
                if length or width is None:
                    raise ValueError(f"invalid PNG IEND: {path}")
                seen_end = True
                break
        if not seen_end or stream.read(1):
            raise ValueError(f"incomplete PNG: {path}")
    if not width or not height:
        raise ValueError(f"invalid PNG dimensions: {path}")
    return width, height


def validate(manifest: dict[str, Any], base: Path) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    for key in ("worktree_revision", "dirty", "build_id", "captured_at_utc"):
        if key not in manifest:
            raise ValueError(f"manifest missing required field: {key}")
    states = manifest.get("states")
    if not isinstance(states, list):
        raise ValueError("states must be a list")
    identifiers: set[str] = set()
    for state in states:
        required = (
            "id",
            "platform",
            "route",
            "viewport",
            "png",
            "sha256",
            "size_bytes",
            "pixel_dimensions",
            "source_files",
            "captured_at_utc",
        )
        missing = [key for key in required if key not in state]
        if missing:
            raise ValueError(f"state missing required fields: {', '.join(missing)}")
        if state["id"] in identifiers:
            raise ValueError(f"duplicate state id: {state['id']}")
        identifiers.add(state["id"])
        if state["platform"] == "web":
            if not state.get("server_mode"):
                raise ValueError(f"web state missing server_mode: {state['id']}")
            if not isinstance(state.get("known_artifacts"), list):
                raise ValueError(f"web state missing known_artifacts list: {state['id']}")
        image = (base / state["png"]).resolve()
        if not image.is_file():
            raise ValueError(f"missing PNG for state {state['id']}: {image}")
        actual_hash = sha256(image)
        if actual_hash != state["sha256"]:
            raise ValueError(
                f"PNG SHA256 mismatch for state {state['id']}: expected {state['sha256']}, got {actual_hash}"
            )
        actual_size = image.stat().st_size
        if actual_size != state["size_bytes"]:
            raise ValueError(
                f"PNG size mismatch for state {state['id']}: expected {state['size_bytes']}, got {actual_size}"
            )
        actual_dimensions = list(png_dimensions(image))
        if actual_dimensions != state["pixel_dimensions"]:
            raise ValueError(
                f"PNG dimensions mismatch for state {state['id']}: expected {state['pixel_dimensions']}, got {actual_dimensions}"
            )
        repo_root = Path(__file__).resolve().parents[1]
        for source in state["source_files"]:
            source_path = (base / source["path"]).resolve()
            if not source_path.is_file() or sha256(source_path) != source["sha256"]:
                raise ValueError(
                    f"source fingerprint missing/mismatch for state {state['id']}: {source['path']}"
                )
            if source.get("git_blob_sha256") and source_path.is_relative_to(repo_root):
                if source.get("revision") != manifest["worktree_revision"]:
                    raise ValueError(
                        f"committed source revision mismatch for state {state['id']}: {source['path']}"
                    )
                repo_path = source_path.relative_to(repo_root).as_posix()
                blob = subprocess.run(
                    ["git", "show", f"{manifest['worktree_revision']}:{repo_path}"],
                    cwd=repo_root,
                    capture_output=True,
                    check=False,
                )
                if blob.returncode or hashlib.sha256(blob.stdout).hexdigest() != source["git_blob_sha256"]:
                    raise ValueError(
                        f"committed source blob fingerprint mismatch for state {state['id']}: {repo_path}"
                    )
    for transition in manifest.get("transitions", []):
        if transition.get("from") not in identifiers or transition.get("to") not in identifiers:
            raise ValueError(f"transition references unknown state: {transition}")
        if not transition.get("action") or not transition.get("evidence"):
            raise ValueError("each transition requires action and evidence")
    for platform in ("web", "android", "ios"):
        coverage = manifest.get("coverage", {}).get(platform, {})
        if platform in NATIVE_BLOCKERS and not any(state["platform"] == platform for state in states):
            coverage["status"] = "NOT CAPTURED/UNVERIFIED"
            coverage["blocker"] = NATIVE_BLOCKERS[platform]
        manifest.setdefault("coverage", {})[platform] = coverage
    return states


def render(manifest: dict[str, Any], base: Path) -> str:
    states = manifest["states"]
    coverage = manifest["coverage"]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for state in states:
        grouped.setdefault(state["platform"], []).append(state)
    sections = []
    coverage_rows = []
    for platform in ("web", "android", "ios"):
        items = grouped.get(platform, [])
        info = coverage.get(platform, {})
        status = info.get("status", "CAPTURED" if items else "NOT CAPTURED/UNVERIFIED")
        blocker = info.get("blocker", "")
        modes = sorted({state.get("server_mode", "") for state in items if state.get("server_mode")})
        modes.extend(
            [info["server_mode"]] if info.get("server_mode") and info["server_mode"] not in modes else []
        )
        artifacts = sorted(
            {artifact for state in items for artifact in state.get("known_artifacts", [])}
            | set(info.get("known_artifacts", []))
        )
        coverage_details = "<br>".join(
            html.escape(value) for value in artifacts + ([blocker] if blocker else [])
        )
        coverage_rows.append(
            f"<tr><th>{html.escape(platform.title())}</th><td>{html.escape(status)}</td>"
            f"<td>{html.escape('; '.join(modes) or '—')}</td><td>{coverage_details or '—'}</td></tr>"
        )
        cards = []
        for state in items:
            png = html.escape(Path(state["png"]).as_posix(), quote=True)
            state_id = html.escape(state["id"], quote=True)
            sources = "<br>".join(
                html.escape(
                    f"{source['path']} · SHA256 {source['sha256']}"
                    + (
                        f" · Git blob SHA256 {source['git_blob_sha256']} @ {source['revision']}"
                        if source.get("git_blob_sha256")
                        else ""
                    )
                )
                for source in state["source_files"]
            )
            known = "<br>".join(html.escape(item) for item in state["known_artifacts"])
            server_mode = html.escape(state["server_mode"])
            pixel_dimensions = html.escape(str(state["pixel_dimensions"]))
            checksum = html.escape(state["sha256"])
            metadata = (
                f'<p class="capture-environment"><b>Server mode:</b> {server_mode}<br>'
                f"<b>Known non-product artifacts:</b><br>{known}</p>"
            )
            observation = html.escape(state.get("observed_confirmation", "UNVERIFIED"))
            cards.append(f"""<article class="frame" id="{state_id}">
<h2>{state_id}</h2><p>{html.escape(state["route"])} · {html.escape(str(state["viewport"]))}</p>
<a href="{png}" target="_blank" rel="noreferrer"><img src="{png}" alt="Original capture {state_id}"></a>
<p>PNG SHA256 <code>{checksum}</code><br>{state["size_bytes"]} bytes · {pixel_dimensions} px</p>
<p>Revision {html.escape(str(manifest.get("worktree_revision", "UNVERIFIED")))} · dirty {html.escape(str(manifest.get("dirty", "UNVERIFIED")))} · build {html.escape(str(manifest.get("build_id", "UNVERIFIED")))} · captured {html.escape(str(state.get("captured_at_utc", "UNVERIFIED")))}</p>
<p>Source fingerprints:<br>{sources}</p><p><b>Observed UI confirmation:</b> {observation}</p>{metadata}
<details class="inspector"><summary>Open original-size 1:1 pannable inspector</summary>
<div class="pan"><img src="{png}" alt="Original-size inspector for {state_id}"></div><p><b>Observed UI confirmation:</b> {observation}</p>{metadata}</details></article>""")
        if not items:
            cards.append(
                f'<p class="empty">No captured frames. {html.escape(blocker or "Coverage is unverified; no screenshots supplied.")}</p>'
            )
        sections.append(
            f'<section><h1>{html.escape(platform.title())} · {html.escape(status)}</h1><div class="flow">{"".join(cards)}</div></section>'
        )
    edges = []
    for transition in manifest.get("transitions", []):
        edges.append(
            f"<li><a href='#{html.escape(transition['from'], quote=True)}'>{html.escape(transition['from'])}</a> → <a href='#{html.escape(transition['to'], quote=True)}'>{html.escape(transition['to'])}</a>: {html.escape(transition['action'])} — evidence: {html.escape(transition['evidence'])}</li>"
        )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Hunt · UI flow evidence</title>
<style>body{font:15px system-ui;background:#f4f6f8;color:#20242b;margin:24px}h1{border-bottom:2px solid #1677ff;padding-bottom:8px}.flow{display:flex;align-items:flex-start;gap:24px;overflow:auto;padding:18px}.frame{flex:0 0 auto;width:min(340px,80vw);background:white;border:1px solid #cbd2dc;border-radius:8px;padding:14px;box-shadow:0 2px 8px #192b4018}.frame img{display:block;width:auto;height:auto;max-width:none;max-height:none;transform-origin:top left;cursor:zoom-in}.frame a{display:block;max-width:100%;max-height:65vh;overflow:auto;border:1px solid #dce2e9}.frame code{overflow-wrap:anywhere}.inspector{margin:10px 0}.pan{max-width:100%;max-height:70vh;overflow:auto;border:1px solid #cbd2dc}.empty{padding:20px;background:#fff;border-left:4px solid #1677ff}.edges,.coverage{background:white;padding:10px 24px}.edges a{color:#075fd1}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid #dce2e9}td{overflow-wrap:anywhere}</style><h1>Hunt · UI/UX flow evidence</h1><p>Only supplied, checksum-verified application screenshots are shown. Open an image in a new tab for unscaled 1:1 inspection; scroll within the image viewport to pan. Empty coverage is not a mock frame.</p>
"""
        + '<section class="coverage"><h1>Platform coverage and capture environment</h1><table><thead><tr><th>Platform</th><th>Coverage</th><th>Server mode</th><th>Known artifacts / blockers</th></tr></thead><tbody>'
        + "".join(coverage_rows)
        + "</tbody></table></section>"
        + "".join(sections)
        + '<section class="edges"><h1>Verified transitions</h1><ul>'
        + "".join(edges)
        + "</ul></section></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate(manifest, args.manifest.resolve().parent)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(manifest, args.manifest.resolve().parent), encoding="utf-8")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"capture board export failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
