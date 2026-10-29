# Hunt UI flow and capture evidence

`artifacts/clients/hunt-ui-flow.html` is an evidence board, not a mockup. It contains six manager-approved original web screenshots from the committed Hunt UI at `801074b239760ced173ddebd62cce8635d59dbd8`; each source PNG's SHA256, byte size and pixel dimensions are revalidated by `scripts/export-ui-board.py`. Source-file fingerprints are recorded against the committed route/component/style files. The board shows each original image at 1:1 in a pannable inspector, with PNG and source fingerprints, revision, dirty state, build id, server mode and known tooling artifacts.

## Known capture fidelity limitation

The approved screenshots were taken while the Next.js development server (`npm run dev`) was running. Each includes the round **N** Next.js dev-tools indicator at bottom-left. That indicator is development tooling, not part of Hunt. Every manifest state records `server_mode: "next dev (development server)"` and a `known_artifacts` note, repeated in each frame/inspector and the platform coverage table. Do not describe the badge as Hunt UI. No further Haiku/browser run is authorized at the current Claude weekly quota. Once quota resets (about 20 hours from the manager's 23:02 notice), the recommended fidelity follow-up is to run `npm run build`, start the production web app with `npm run start -w @hunt/web` on port 3201 (with the platform API on 8201 and gateway on 3202), and repeat the same six-state plan once through the separately managed Haiku browser lab. Do not claim that production recapture happened until it has.

## Captured states

The six verified web captures are desktop `/`, desktop `/hunt`, home with the opt-in synthetic voucher visibly labelled `SYNTHETIC · DEMO` / `SYNTHETIC-VOUCHER-2099`, phone `/`, phone `/discover`, and phone `/saved`. Screenshots show voucher-window evidence, cap, minimum spend, checkout payment, cashback separately, eligibility and as-of information. They make no price, availability or countdown claim. The five manifest transitions cite the actual Haiku final report's click references (ref_2, ref_5, ref_13, ref_9, ref_15), tool route outputs, and follow-up DOM reads. Do not substitute planned steps or infer unrecorded interactions.

## Native coverage

- Android: NOT CAPTURED/UNVERIFIED — no Android SDK/emulator; unavailable old runtime captures.
- iOS: NOT CAPTURED/UNVERIFIED — no Xcode; unavailable old runtime captures.

No native placeholder, web mockup or test fixture is a native capture.

## Manifest schema version 1

Top-level fields: `schema_version`, `worktree_revision`, `dirty`, `build_id`, `captured_at_utc`, `states`, `transitions`, and `coverage`. Each state records id/platform/route/viewport, relative PNG path/SHA256/size/pixel dimensions/UTC capture time, source-file fingerprints and server environment. Web states require `server_mode` and `known_artifacts`. Each transition records `from`, `to`, the actual `action`, and observed `evidence`; do not invent transitions. Coverage includes platform status, server mode, known artifacts or the precise native blocker. All paths are relative to the manifest. Missing or mismatched PNG/source files fail closed.
