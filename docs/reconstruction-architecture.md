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
