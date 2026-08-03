# Resource System

The public repository contains no original resources. A tester supplies a
local resource root and generates a metadata-only manifest with
`liminal-gate-build-resource-catalog`. Each served relative path is pinned to
the local file's SHA-256; unmanifested paths and unsafe traversal are refused.

Generated manifests and payloads remain under ignored local directories.
Details and commands are in `developer-reference.md` and the README.

The private on-device builder emits schema version 2 for the same URL mapping.
Each entry names a safe APK member plus its exact size, SHA-256, and content
type. Payload members must be unique, unencrypted, free of data descriptors,
and stored without compression. Android validates that central-directory
metadata at startup and streams the member from the locally signed APK. It does
not extract or re-hash the complete 900-plus-MiB tree during every launch; the
source-hash-guarded build and APK signature are the payload integrity boundary.
Small runtime/catalog members are separately digest-checked before atomic
extraction to app-private storage.
