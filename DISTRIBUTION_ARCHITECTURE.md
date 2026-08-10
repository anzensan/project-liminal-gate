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

## Two deployments, one feature set

There are two ways to run this server and they must always stay at feature
parity:

- the **dedicated server**, which a tester reaches over the local network and an
  operator configures with flags and paths;
- the **all-in-one package**, which embeds the same Python server in the client's
  own APK and serves it over loopback.

They are the same server, so a change that reaches one has to reach the other.
Nothing enforces that automatically, and the two take their configuration from
different places: the dedicated route reads an operator's command line, while
the on-device route bakes its configuration into `write_server_runtime` and its
catalogs into the APK at build time. That asymmetry is where they drift. A
policy flag added to one launcher and not the other, or a catalog regenerated
for one and not rebuilt into the other, produces a defect only some testers can
reproduce -- and the on-device tester cannot fix it by restarting anything.

Two habits keep it honest. Every change states which deployment it needs -- a
server restart, an APK rebuild, or both -- because "server restart only" is
false for on-device testers whenever server code changes. And any new server
policy is added to `standard_policy_fields` rather than to a single launcher, so
both routes pick it up from one place.

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
