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

## Attack of Coin Creeps card fallback

The final client catalog and retained resource archive omit the complete
`sp1003` banner family even though the client advertises Chapters 1003-1 through
1003-3. Guided setup therefore derives three catalog aliases from the retained
`sp3003-1` record. Exact operator-owned `sp1003` bundles are preferred when
present. Otherwise setup derives three user-local ENCA bundles from retained
`sp3003-1` Coin Creeps-family art, changing only the internal texture, container,
and bundle names required by each requested identity. The public-data transport
serves the plain and client-MD5 URLs. This is labeled local presentation policy,
not recovered original artwork. Chapter/section identity and battle state are
not aliased.
