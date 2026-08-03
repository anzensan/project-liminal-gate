# Private on-device compatibility server

Status: build path implemented; physical-client acceptance is pending.

This page records architecture and validation evidence. For the complete
operator procedure, use [Run the server inside the Android APK](on-device-setup.md).

## Reported approach

The local build path creates one privately signed APK from a tester-owned,
reviewed Terra Battle APK and matching Android resource tree. It starts its
compatibility server at `http://127.0.0.1:8002`, verifies a matching `/healthz`
build ID over real HTTP, and only then starts Unity. This is build evidence, not
yet physical-client acceptance evidence.

If practical, this could remove the current requirement for a separate
computer running Python and a stable LAN address. The client would instead
connect to a server bound only to Android loopback, such as
`http://127.0.0.1:8002`.

## Build path

1. The reviewed literal patch redirects API and resource traffic to fixed
   Android loopback only; it never exposes a LAN listener.
2. The replacement launcher starts embedded Python in the app process and
   blocks Unity on a matching health response, with retry/diagnostics on error.
3. The complete tester-owned resource tree is packaged in the private artifact;
   resources stream from the signed APK rather than a second extracted copy.
4. Durable state is app-private. `--seed-state` embeds an optional first-install
   seed only; it never replaces an existing save.

The public project distributes source/build logic only. APKs, resources,
signing keys, state, Gradle cache, and generated packages stay ignored and
private.

## Build and install

```sh
python3 -m liminal_gate.on_device_setup --check
python3 -m liminal_gate.on_device_setup --device YOUR_ADB_SERIAL
```

`--check` changes nothing and validates the same inputs used by the real build.
The combined APK contains `arm64-v8a` and `armeabi-v7a`; the device must be API
24+, support at least one of those ABIs, and have at least 4 GiB free before
installation. `--prepare-only` creates no device
changes. `--replace-existing` may uninstall a mismatched local signature and
therefore clears that app's data.

The [operator guide](on-device-setup.md) covers the required private input
layout, tool installation, device selection, expected success output, startup
verification, updates, save limitations, and failure recovery.

## Current evidence

- The immutable final APK is accepted only at SHA-256
  `f2c0ffa188255f4694f0f60e898a58b372c2cc3fff7dd312a01d593189bd7a15`.
- The private assembler changes the launcher activity and minimum SDK, removes
  obsolete signatures, retains the reviewed client payload, and adds host DEX,
  Chaquopy 17/Python 3.11, and both ARM ABIs before local alignment/signing.
- The server and Unity share one Android process. The host invokes Python,
  polls real loopback HTTP for the same payload-bound 64-hex build ID, and
  constructs `UnityPlayer` only after service, status, and build ID all match.
- The packaged resource manifest records exact member names, sizes, and
  SHA-256 values. Resource members are `ZIP_STORED` and streamed from the
  signed APK; only small generated catalogs/configuration are copied into app
  storage.
- Save state, replay records, event diagnostics, and backups remain under the
  app's private files directory. A seed uses atomic create-if-absent behavior.
- The loopback listener also answers `GET`/`POST /local/state`, the operator
  save-transfer route that [`on_device_state`](saves.md#the-on-device-save)
  drives over `adb forward`. Export serializes the same document the server
  would persist, so it cannot lag the running save; import replaces the
  in-memory copy and the file together, rotating the replaced save into
  `state.json.bak.1`. Both are refused unless the listener is bound to
  loopback, which keeps a LAN-bound workstation server from publishing a
  downloadable, replaceable save to the network. On the device itself loopback
  is not a privilege boundary: while the app runs, any other app on that device
  can read and replace the save.
- JVM and Python lifecycle/resource tests cover readiness, extraction, retry,
  seed preservation, direct streaming, and server close behavior.
- The APK hashes recorded below predate the save-transfer route and no longer
  describe a current build. They stand as the evidence for the run they came
  from; a rebuild must record its own.
- The complete local build packaged 11,806 resources (940,138,388 bytes),
  passed ZIP-header, alignment, and v2/v3 signature verification. The final
  source-exact APK is SHA-256
  `aeba11eade3b507d62403ee806b3e7390bb3a2abced03a0219e3ec4633685ef0`
  with payload ID
  `53d043cbb585337d19a749ef1a1735b31c5499bbe00c1376123d9600900fff93`.
  A preceding full-resource payload launched on API 34 ARM64: real loopback
  HTTP returned its matching build ID and one selected resource's exact 129,018
  bytes/SHA-256 before and after force-stop relaunch. The exact component
  launcher also returned `Status: ok`. Large packages use ADB
  `--no-incremental`; incremental install falsely reported success during
  validation without leaving the package installed. The final APK did not
  replace that validation build because the emulator had only 1.2 GiB free,
  so its device acceptance remains pending.

## Remaining acceptance boundary

- Install the full-resource artifact on physical ARM64 hardware and an
  `armeabi-v7a` emulator or device.
- On each lane, record cold start, force-stop/relaunch, low-memory/process-death
  recovery, and a resource response through the real client transport.
- On physical hardware, complete signup/login, the tutorial Pact, and Chapter
  2-1 with before/after state plus exact retry and restart proof.
- Record generated APK hash, package/SDK/ABI/launcher inspection, signing and
  alignment verification, and device logs together. A successful build or
  health response alone does not certify gameplay.
