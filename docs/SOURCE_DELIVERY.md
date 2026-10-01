# Reproducible source-only delivery

`tools/build_source_delivery.py` is a separate stdlib-only packaging boundary.
It does not invoke `build_windows_delivery.py`, PyInstaller, provider SDKs,
credentials, or the network. It does not change Invest's runtime or existing
acceptance gates.

## Build and verify

Select a full lowercase immutable commit ID independently from trusted GitHub
history or a reviewed local commit. A branch, tag, abbreviated hash, or `HEAD`
is deliberately not accepted by the builder. Git and Python 3.10+ are required;
all selected objects must already exist locally. No fetch is attempted.

```sh
python tools/build_source_delivery.py build --repo . --commit FULL_COMMIT_ID --output /new/path/Invest-Source.zip
python tools/build_source_delivery.py build --repo . --commit FULL_COMMIT_ID --output /new/path/Invest-Source-repeat.zip
python tools/build_source_delivery.py verify --repo . --commit FULL_COMMIT_ID --archive /new/path/Invest-Source.zip --extract /new/path/verified-source
```

Output parent directories must exist. Output files and extraction destinations
must not already exist, including symlinks. Failed extraction removes only its
newly created destination. All bytes are verified before any extraction write;
this is rollback-cleaned extraction, not a concurrently visible atomic directory
swap. The extracted repository is under `verified-source/invest-source/`.

Two builds of the same admitted commit produce byte-identical ZIPs, independent
of dirty/untracked files, worktree line endings, file modification times, host
permissions, and compression-library versions. Members are sorted, stored
uncompressed, and have fixed 1980 timestamps and regular `0644` archive modes.
Original Git modes are recorded separately; executable source scripts are
included only as non-executable text. No executable/native binary distribution
is produced.

`SOURCE_MANIFEST.json` records the exact commit/tree, sorted paths, byte lengths,
Git blob IDs, SHA-256 content hashes, and original/archive modes. The manifest
excludes itself from the file list; the ZIP includes it as one additional entry.
The CLI JSON report records the complete archive SHA-256 and byte/entry counts.

The verifier rebuilds the canonical archive from the separately selected trusted
commit and requires exact byte equality. A self-consistent manifest or an
archive's own SHA-256 does **not** authenticate upstream provenance. Verification
rejects changed or foreign manifests, content corruption, duplicate/extra ZIP
members, metadata changes, links, unsafe paths, and trailing bytes. It does not
parse untrusted ZIP data until that whole-archive comparison succeeds.

## Source admission and bounds

The builder reads Git commit/tree/blob objects, never worktree payloads, index
contents, Git filters, or replacement refs. It independently checks each object
hash. Git transport is denied and lazy fetching disabled; inherited Git overrides
and credential variables are not passed to Git.

- Include the current source, tests, examples, documentation, governance history,
  workflows, third-party source, LICENSE/NOTICE files, and provenance metadata
- Explicitly omit `legacy_app/` and `legacy_research/`, which contain legacy
  compiled `.bin` chunks
- Omit untracked files inherently; omit known private/runtime/generated paths
  such as `.env*`, `.invest/`, `.git/`, database/cache files, build outputs,
  credentials, and virtual environments even if accidentally committed
- Admit UTF-8 text in explicit source roots/file types; permit only the two named
  `examples/SYNTHETIC_DEMO_*.csv` fixtures as CSV, not arbitrary market/private data
- Reject unknown file types/roots, binary/control bytes, symlinks, submodules,
  unsafe or nonportable paths, case collisions, and a source manifest collision
- Limit included files to 5,000, content to 64 MiB, one blob to 4 MiB, traversed
  tree data to 4 MiB, tree entries to 10,000, archive size to 80 MiB, and archive
  paths to 240 UTF-8 bytes; test/API limits may only lower these ceilings

Excluded directories are not traversed. Text/path admission is not a secret
scanner: review the selected commit before delivery, especially future changes
to otherwise allowed source/JSON/documentation. Unknown inputs fail closed;
expand the explicit policy only after review.

## Extracted-source acceptance

`.github/workflows/source-delivery.yml` checks out the exact PR head SHA rather
than GitHub's synthetic merge commit. On Linux and Windows it:

1. Runs the focused boundary/adversarial tests without modifying existing gates
2. Builds twice, requires identical bytes, verifies against that trusted local
   head, and extracts into a new temporary directory
3. Builds a wheel from the extracted source and installs its core dependencies
4. Runs the extracted `tools/native_restore_smoke.py` in default SDK-free mode
   from a separate runtime directory. Its isolated child imports the installed
   wheel, blocks optional SDK imports/external Python network, and restores the
   committed synthetic fixture with identity and raw-export preservation
5. Uploads only `Invest-Source.zip`, `SOURCE_MANIFEST.json`, and a compact
   `verification.json` with the exact head/tree, hashes/counts, duplicate-build
   equality, trusted verification, and extracted-wheel recovery results

The workflow uses a read-only repository token and does not publish a release or
deploy. Dependencies are installed in CI as a separate verification step; they
are not bundled in the source ZIP. CI success is scoped to the corresponding
artifact's exact commit. Local reproduction with preinstalled core dependencies,
setuptools, wheel, and Node can avoid dependency network access:

```sh
python -m pip wheel --no-deps --no-build-isolation --wheel-dir /new/wheels /new/path/verified-source/invest-source
python /new/path/verified-source/invest-source/tools/native_restore_smoke.py /new/wheels
```

Run these from a separate runtime directory, not either source checkout. The
smoke installs the built wheel into another fresh target using `--no-index` and
executes an isolated Python child, so neither source tree is the Invest runtime.

This source artifact does **not** establish Windows EXE acceptance, browser
layout acceptance, or actual-user-device acceptance. The intermittent optional
MLflow initialization limitation remains unresolved; SDK-free restore does not
exercise, fix, or supersede that limitation.
