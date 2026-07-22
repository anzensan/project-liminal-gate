# Developer reference

This page collects tools and modes that are not required for a normal tester.

## Server modes

The README uses `liminal-gate-bootstrap-server` with the included compatibility
profile. For a generic empty foundation server, use:

```sh
python3 -m liminal_gate.server --data-dir user-data
```

The bootstrap server also accepts a user-local profile and optional event log.
Its event log records only method, route, status, and timestamp; it excludes
query strings, bodies, tokens, and digests.

## Resource serving

Resource serving requires both `--resource-root` and `--resource-manifest`.
Build the manifest instead of editing it by hand:

```sh
liminal-gate-build-resource-catalog \
  --resource-root /path/to/user-resources \
  --output-manifest user-data/resources.json
```

The resulting manifest maps local regular files to `/resources/` paths and
pins each file's SHA-256. Files absent from the manifest are not served.

## APK tools

The tester quick start uses the reviewed legacy-client plan generator. The
project also includes:

- `liminal-gate-apply-apk-plan` — applies a source-hash-guarded user plan.
- `liminal-gate-generate-il2cpp-plan` — creates a guarded local plan for
  user-selected ASCII literal replacements.
- `liminal-gate-sign-apk` — aligns, signs, and verifies an APK with
  user-supplied Android tools and key material.
- `liminal-gate-import-input` — writes local APK/resource structural metadata.
- `liminal-gate-import-bootstrap-profile` — derives a local bootstrap profile
  from a user-owned JSONL capture after removing session material.

Run any tool with `--help` for its exact arguments.

## Release checks

Before publishing changes, run these from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m liminal_gate.release_preflight
python3 -m liminal_gate.release_audit
```

The preflight checks that no prohibited local material entered the source tree;
the audit checks that this checkout remains independently releasable.

## Project references

- [Compatibility scope](../COMPATIBILITY_SCOPE.md)
- [Parity roadmap](../PARITY_ROADMAP.md)
- [Distribution architecture](../DISTRIBUTION_ARCHITECTURE.md)
- [Release scope](../RELEASE_SCOPE.md)
- [Publication checklist](../PUBLICATION_CHECKLIST.md)
- [Contributing](../CONTRIBUTING.md)

Return to the [README](../README.md) for the tester path.
