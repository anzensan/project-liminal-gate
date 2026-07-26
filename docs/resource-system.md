# Resource System

The public repository contains no original resources. A tester supplies a
local resource root and generates a metadata-only manifest with
`liminal-gate-build-resource-catalog`. Each served relative path is pinned to
the local file's SHA-256; unmanifested paths and unsafe traversal are refused.

Generated manifests and payloads remain under ignored local directories.
Details and commands are in `developer-reference.md` and the README.
