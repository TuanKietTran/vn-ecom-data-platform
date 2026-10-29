# Publish datasets on Hugging Face

Hugging Face Hub hosts public datasets for free. A dataset repository is Git-backed and versioned: commits, branches, tags, and history let users pin or compare snapshots. The Hub dataset viewer can preview supported tabular files in the browser; Parquet is a native, efficient format for this, with column and row-group metadata enabling filtering and downloads without fetching an entire dataset. Viewer availability and previews depend on file size, schema, and Hub processing; hosting does not guarantee every file will render in the viewer.

## What belongs there

Publish data you have the right to redistribute. In this project, appropriate candidates include generated `synthetic` data and public-source records only after reviewing each source's terms, applicable law, and any personal or sensitive information. `licensed` feeds and affiliate/provider data require explicit redistribution permission. Do not upload private seller API results, credentials, access tokens, or data whose license or terms prohibit redistribution. Publicly accessible does not mean public-domain or redistributable.

Prefer curated, documented Parquet exports (for example, derived silver/gold tables) over raw landing data. Include a dataset card describing provenance, collection dates, schema, caveats, and license; only declare a license you are authorized to grant. Remove secrets and unnecessary identifiers before publishing. A public repository is visible to everyone, and a later deletion does not undo prior downloads or clones.

## Publish with this project

The intended project command is `vnecom publish-hf REPO_ID [--yes] [--private | --public] [--dry-run] [--output PATH]`. `REPO_ID` is your Hugging Face namespace/repository name (for example, `YOUR_USERNAME/YOUR_DATASET`). Create or select the dataset repository under your own account or organization, and create a write-access token at https://huggingface.co/settings/tokens. The command uses the token from `HF_TOKEN`; never put it in a repository or share it.

Uploads require both `HF_TOKEN` and explicit `--yes`. Repositories are private by default; use `--public` only when you explicitly intend public release. `--private` makes the private choice explicit. `--dry-run` does not contact the Hub or upload; it writes the allowlisted, redacted Parquet export locally and reports total rows, per-source row counts, and size. Use `--output PATH` to select the local export directory. A dry run does not require an upload confirmation or Hub token.

First run a local dry run; no token or upload confirmation is needed:

```bash
vnecom publish-hf YOUR_USERNAME/YOUR_DATASET --dry-run --output ./hf-export
```

Review the export and reported source counts. For the actual upload, enter the token silently at the prompt so it is not included in the command text or shell history, then explicitly opt into public visibility:

```bash
read -rsp 'HF_TOKEN: ' HF_TOKEN; echo; export HF_TOKEN
vnecom publish-hf YOUR_USERNAME/YOUR_DATASET --yes --public --output ./hf-export
unset HF_TOKEN
```

For the default-private upload, omit `--public` (or specify `--private`). Review the repository visibility before uploading. The token is yours and remains local; this project does not create repositories or manage Hugging Face credentials.

Each upload creates versioned repository history, but it is not a substitute for a data-release process: choose meaningful commits/tags, document schema changes, and avoid treating mutable `main` as a permanent citation. Large files may use Git LFS; review current Hub limits and any storage/bandwidth policies before uploading. Viewer processing can be delayed or fail for unsupported schemas or large datasets. Check the repository page after upload and provide a commit or tag when you need a reproducible reference.
