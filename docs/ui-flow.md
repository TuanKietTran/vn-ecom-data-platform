# Hunt UI flow and capture evidence

This is an evidence artifact specification, not a mockup. The exported board at `artifacts/clients/hunt-ui-flow.html` contains only original screenshots captured from the real running application and listed in `artifacts/clients/capture-manifest.json`. `scripts/export-ui-board.py` verifies image checksum, byte size, pixel dimensions and source-file fingerprints before producing the HTML. The images are viewable at their original 1:1 size in a pannable viewport/new tab. Transitions are listed only when their action and evidence are recorded in the manifest.

## Coverage

- Web: NOT CAPTURED/UNVERIFIED in this work session. Capture awaits an actually running web application and a separately managed real interactive Claude Haiku browser lab; this worker must not create browser screenshots.
- Android: NOT CAPTURED/UNVERIFIED — no Android SDK/emulator; unavailable old runtime captures.
- iOS: NOT CAPTURED/UNVERIFIED — no Xcode; unavailable old runtime captures.

No empty-state illustration, native-device mock, HTML rendering, test fixture or placeholder is a capture. The board shows honest empty coverage where evidence is absent. Do not infer inaccessible flows or label them complete.

## Manifest schema version 1

The JSON top-level fields are `schema_version`, `worktree_revision`, `dirty`, `build_id`, `captured_at_utc`, `states`, `transitions`, and `coverage`. Each state provides `id`, `platform`, `route`, `viewport`, `png`, `sha256`, `size_bytes`, `pixel_dimensions` (`[width,height]`), `source_files` (array of `{path, sha256}` fingerprints) and `captured_at_utc`. Each transition provides `from`, `to`, `action` and `evidence`. Coverage records a status and, when blocked, its exact blocker. All paths are relative to the manifest. PNG/source mismatches and missing files fail closed.
