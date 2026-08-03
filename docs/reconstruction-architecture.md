# Reconstruction Architecture

Project Liminal Gate is a source-only local compatibility layer:

1. tester-owned inputs are hashed and checked locally;
2. strict importers produce metadata/catalog projections without copying
   protected material into the repository;
3. the guided setup creates a local, source-hash-guarded client build;
4. `bootstrap_server` serves the confirmed bootstrap path plus explicitly
   enabled local-policy catalogs;
5. `BootstrapState` atomically persists per-account state and retry responses;
6. `event_log` emits privacy-bounded route diagnostics;
7. release preflight/audit enforce the public source boundary.

Protocol parsing remains strict and unknown behavior fails visibly. The next
implementation slice should always be the smallest reproducible client-visible
failure beyond the current checkpoint.

## Private on-device deployment

The on-device route reuses that server; it is not a second compatibility
implementation. Local setup first runs the same reviewed input/catalog
derivations, redirects the client to `http://127.0.0.1:8002`, and builds a
source-only Android host with Chaquopy 17 and Python 3.11. The private assembler
then combines the host with the tester-owned client and full resource tree,
raises the package minimum to API 24, and retains both `arm64-v8a` and
`armeabi-v7a`.

`HostedActivity` starts Python in the application process and polls `/healthz`
for the package's exact build ID. It does not construct `UnityPlayer` until the
response matches. Small signed configuration/catalog members are verified and
copied atomically to app-private storage; large `ZIP_STORED` resources stream
directly from the APK. Save state and replay records remain ordinary
`BootstrapState` data in app-private storage, including atomic commit and
restart behavior. An optional seed is create-if-absent and cannot replace a
played save.

Generated APKs, resources, local keys, state, and Gradle/build products remain
ignored tester artifacts. The repository publishes only the host source and
reproducible assembly logic.
