# Multi-account server: design

Status: **Implemented for trusted-LAN household use with source-IP binding.**
Cookie-based routing remains unverified and is not used.

## 1. Goal

Let several people in one household each keep their own save against a single
running server, instead of one save per server instance — and let one person
open their own save from more than one device.

**"Together" here means concurrent, isolated saves on shared hardware.** The
original game's friends, PvP, co-op, raid, and shared-HP systems are out of
scope and remain disabled. Nothing in this design makes players visible to one
another, and the documentation must say so plainly, or "a family playing
together" will be read as shared-world multiplayer.

## 2. What already works

Account **storage** is multi-account today and needs no schema change.

Accounts are keyed by the client-supplied device UUID. The signup response
template is `{"success": true, "id": "{uuid}"}`, and the profile's
`account_binding` maps `signup_response_field = "id"` and
`login_query_field = "uuid"`. Two devices that sign up produce two independent
account records in the same state file, each with its own userdata, wallet,
progress, and per-account request-replay caches.

Concurrency is also already in place: the server is a `ThreadingHTTPServer`, so
simultaneous clients are served rather than queued.

## 3. Routing constraint and implemented policy

Account **routing** is the problem, and the cause is in the client protocol
rather than in this server's design.

Only `signup` and `login` carry `uuid`. Every other `/gd/*` request identifies
itself with just `otk` and `requestID`. And `otk` is not a session key — it is

```
MD5HEX(str(GetUnixTime() / 3) + "mist_guardians_keycode")[16:32]
```

a **pure three-second time bucket** with no account, device, or session
component (`docs/server-protocol.md`).

The consequence is decisive:

> Two clients playing at the same moment send **byte-identical `otk` values**.
> A map from `otk` to account cannot separate them, even in principle.

The server therefore associates the request source IP with an account at
signup/login, the two routes that carry `uuid`. A later rotated OTK is bound to
that host's identified account. Once any host ownership exists, an unidentified
LAN host is refused instead of inheriting the active account. Legacy saves
without host bindings allow one first host to claim the existing account and
then enforce the same rule.

This is a trusted-LAN compatibility policy, not cryptographic authentication.
Changing address requires login again; clients hidden behind the same source
address cannot be distinguished.

## 3a. Linked devices

The client protocol has no account system: the silently stored device UUID is
the only credential, and the wire has no transfer route. One player on two
devices is therefore operator bookkeeping, like `adopt`. The state file holds
an `account_aliases` map from a linked device's UUID to the account it plays;
signup and login — the only identity-bearing routes — resolve through it, so a
linked device's own UUID opens the shared save, and a linked device that clears
its app data re-signs-up into the shared save rather than a fresh one. A UUID
may name an account or an alias, never both; the server refuses to load a save
that violates this. The map is written only by
`python3 -m liminal_gate.account_state link` / `unlink`, never by the wire.

Linking shares one save; it does not merge concurrent play. Two linked devices
playing at once are last-write-wins, so the documentation tells players to play
one device at a time (`saves.md`).

## 4. Alternatives retained as boundaries

### Server-issued session cookie

- **Confidence: strongly inferred, never live-verified.**
  It is deliberately not fabricated into the public implementation without a
  surviving-client transport capture.

### One server instance per player

Each player gets their own `--data-dir` and `--port`, and therefore their own
APK built against that port.

- **Available now with no code change at all.** Both flags already exist.
- Costs one process and one APK build per player.
- This remains the fallback for clients that share a source address.

## 5. Certification

Automated coverage proves independent host routing, refusal of an unidentified
host, legacy-save claiming, durable host mappings, per-account state, and
restart replay. A physical two-device soak remains useful for:

- independent progress and independent wallets;
- correct replay when each client retries its own request;
- correct resumption after a server restart;
- correct resumption after each app is force-stopped and relaunched;
- an unroutable request returning a clean unauthorized response rather than
  being attached to the wrong account.

## 6. Explicit non-goals

No friends, PvP, co-op, raids, shared HP, ranking, or any social feature. No
in-game account UI or credentials — device identity moves only through the
operator's `adopt` and `link` commands. No save merging between devices playing
concurrently. No remote or internet-facing exposure: this remains a
local-network server.
