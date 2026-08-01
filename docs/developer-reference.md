# Developer reference

This page collects tools and modes that are not required for a normal tester.

## Server modes

The README uses `liminal-gate-bootstrap-server` with the included compatibility
profile. For a generic empty foundation server, use:

```sh
python3 -m liminal_gate.server --data-dir user-data
```

The bootstrap server also accepts a user-local profile and optional event log.
The log excludes query strings, request bodies, tokens, authentication
digests, account IDs, rosters, and item data. In addition to method, route,
status, and timestamp, a mutation may record field names, non-secret
stage/progress values, account phase booleans, and aggregate Coin/EXP
settlement values. A malformed non-form body is represented only by its
SHA-256 and byte length. Review an excerpt before publishing it; see
`CONTRIBUTING.md` for the privacy checklist.

A refusal to parse a body — any `unsupported_*` result — additionally records
`request_shapes`: for each JSON-valued form field, its JSON type, entry count,
how many distinct key sets its rows use, and the value types seen against each
key. The field list alone cannot explain such a refusal, because a supported
form and a refused one can carry the identical field names. Key names are
echoed only when this server already models them; anything else is counted,
so no string from the body itself can reach the log.

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
- `liminal-gate-import-native-encounters` — reads the ARM64 chapter battle
  programs out of a reviewed APK, using the user's Il2CppDumper `dump.cs` and a
  local `objdump`; feeds `liminal-gate-generate-story-outcomes`. See
  [Advanced local configuration](advanced-configuration.md#composing-a-story-outcome-catalog-from-your-own-recovered-drops).
- `liminal-gate-import-scenario-encounters` — covers the chapters the native
  import cannot: 2--7 have no compiled battle program, and their encounters are
  placed by Lua the client runs on an embedded MoonSharp VM. Reads the
  `Chapter{N}` `TextAsset` objects out of a reviewed APK, decodes the MoonSharp
  binary dump, and emits the same stage schema under separately validated
  provenance. Feeds `liminal-gate-generate-story-outcomes --scenario-encounters`.
  Needs UnityPy but no `dump.cs` type trees; it does need `dump.cs` itself for
  the `Enemies` enum.

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

None of the three runs the setup pipeline: the unit suite replaces the IL2CPP
dump, the master-data import, the catalog derivations, and the signing with
fakes. After a change that could reach any of those, rehearse setup on a clean
copy of the source and compare the result with a run you already trusted:

```sh
python3 -m liminal_gate.setup_rehearsal \
  --apk /path/to/your/terra-battle.apk \
  --resource-root /path/to/your/resources/data_u2017/android
```

See [Rehearse setup before you trust a change](setup-rehearsal.md).

## Project references

- [Compatibility scope](../COMPATIBILITY_SCOPE.md)
- [Parity roadmap](../PARITY_ROADMAP.md)
- [Distribution architecture](../DISTRIBUTION_ARCHITECTURE.md)
- [Release scope](../RELEASE_SCOPE.md)
- [Publication checklist](../PUBLICATION_CHECKLIST.md)
- [Contributing](../CONTRIBUTING.md)

Return to the [README](../README.md) for the tester path.
