# Possible Future: On-Device Compatibility Server

Status: deferred idea, not implemented or verified.

## Reported approach

One community report described patching the Android client so that opening a
single APK starts a bundled compatibility server and then launches the game
client. This is an architecture lead only. No source, patch, APK hash, runtime
capture, or reproducible build instructions have been reviewed.

If practical, this could remove the current requirement for a separate
computer running Python and a stable LAN address. The client would instead
connect to a server bound only to Android loopback, such as
`http://127.0.0.1:8002`.

## Possible architecture

1. A replacement launcher activity starts an embedded server process or
   service.
2. The launcher waits for a positive readiness check rather than using a fixed
   delay.
3. The launcher starts the original Unity activity.
4. The existing guarded APK routing patch points API and resource requests at
   the loopback origin.
5. Account state, retry records, diagnostics, and locally supplied resources
   use application-owned storage.

The public project would continue to distribute source and build tooling only.
A tester would supply the original APK and resources locally and generate the
combined APK for personal preservation use.

## Unknowns

- Whether the reported server uses embedded Python, Java/Kotlin, or native
  code.
- Whether it runs in the Unity process or an isolated Android process.
- How it remains alive for the complete client session.
- Whether “single APK” includes the downloaded resource set or only the client
  and server runtime.
- How resources are installed, extracted, updated, and integrity-checked.
- Which Android versions and ARM ABIs have been exercised.
- How cold start, force-stop, crash recovery, low-memory process death, retry,
  and durable commit behavior are handled.
- The size and compatibility cost of embedding CPython if the existing server
  is reused without a rewrite.

## Evidence to request

Before treating this as an implementation plan, obtain:

- SHA-256 hashes for the exact source and generated APKs;
- the launcher, manifest, service, DEX/smali, and native-library changes;
- the embedded runtime and version;
- the loopback address and port;
- the resource and account-state storage layout;
- tested Android versions, devices, and ABIs;
- cold-start, relaunch, and force-stop logs; and
- reproducible local build instructions that do not redistribute original game
  material.

## Smallest future proof

Do not begin by porting the complete server. First produce a private,
hash-guarded test build that:

1. starts a minimal server on loopback;
2. waits until it is ready before launching Unity;
3. handles the first real client bootstrap request through the actual transport
   path;
4. serves one manifest-approved local resource;
5. preserves one mutation across force-stop and relaunch; and
6. fails visibly if server startup or storage initialization fails.

Only after that proof should the project choose between embedding the existing
Python server and implementing an Android-native runtime.
