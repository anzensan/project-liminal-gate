# Distribution Architecture

Project Liminal Gate distributes source code only. A tester supplies the
original Android client, matching resources, Android tools, signing key, and
any optional derived catalogs locally.

## Boundary

The public Git repository contains:

- clean-room Python source and tests;
- a compatibility profile containing only reviewed wire structure and local
  policy values;
- source-available documentation and browser tooling;
- no APK, original resource, raw capture, account state, signing secret, or
  generated client build.

Generated files stay beneath ignored `local-input/` and `user-data/`
directories. The release preflight inspects the complete proposed tree,
including `build/` and `dist/`; the release audit additionally rejects dirty
worktrees and prohibited path names anywhere in Git history.

## Runtime

The guided setup:

1. hashes and structurally checks the user-owned inputs;
2. builds a hash-pinned resource manifest without copying resources into Git;
3. creates a source-hash-guarded local APK patch plan;
4. patches, aligns, and signs a generated APK under `user-data/`;
5. runs the compatibility server on the tester's machine.

The server is intended only for a trusted local network. It binds broadly so a
device can connect, but unknown hosts cannot inherit an active account merely
by presenting a new token. Operators must not expose the port to the Internet.

## Publication proof

The publication gate is:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q liminal_gate tests
python3 -m liminal_gate.release_preflight
python3 -m liminal_gate.release_audit
```

A clean archived copy is also checked so ignored local tester output cannot be
mistaken for committed release content.
