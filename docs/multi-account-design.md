# Multi-account server: design

Status: **Design only. Not implemented.** One protocol question must be settled
by experiment before any of this is built.

## 1. Goal

Let several people in one household each keep their own save against a single
running server, instead of one save per server instance.

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

## 3. What does not work, and why

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

This is not a bug that can be tuned out of the existing token map. The server
preserves every previously bound `otk`-to-account association, but uses a
single active-account fallback for a genuinely unknown rotated token. That is
coherent for one client at a time; it is not a safe routing policy for several
concurrent clients. Any real multi-account support has to add an identity
signal that the protocol does not currently provide, and route on that instead.

## 4. Candidate discriminators

### Option A — server-issued session cookie

`AppServerUtil.SaveCookie` reads `Set-Cookie` from a response into the client's
`hsHeader` dictionary, and `MyWWW` copies that stored `Cookie` string onto every
subsequently created request without host, path, or expiry checks. Issuing a
per-account cookie at login would give exact per-client identity with no client
patch, and is closest to what the retired service most likely did.

- **Confidence: strongly inferred, never live-verified.**
  `reports/session_auth_lifecycle.md` records that the clean-room server has
  never sent `Set-Cookie`, that cookie-stateless operation was sufficient for
  every captured phase, and that the exact `SaveCookie` byte handling was left
  open mid-disassembly.
- `hsHeader` is in-memory only. It does not survive an app restart, so login
  must always be able to re-establish the session. It is also not cleared on
  logout.
- The parsing is quirky in ways a naive `Set-Cookie` would trip over: the value
  is split on exact `"; "`, only lowercase `path=` segments are removed, and
  each retained segment is re-prefixed with `"; "`. The issued cookie should be
  kept to a single simple `name=value` pair with no attributes.

### Option B — source IP binding

Bind the account to `client_address[0]` at login and route later requests by
source address.

- Works today with no dependency on unverified client behavior.
- On a home LAN each device has a distinct address, which is exactly the target
  topology.
- Breaks if a DHCP lease moves mid-session; recoverable by re-login.
- Would be wrong behind a shared NAT address, which does not occur here.

### Option C — one server instance per player

Each player gets their own `--data-dir` and `--port`, and therefore their own
APK built against that port.

- **Available now with no code change at all.** Both flags already exist.
- Costs one process and one APK build per player.
- Should be documented as the interim answer regardless of which routing design
  wins, because it needs nothing from this document.

## 5. Recommended sequence

**Step 1 — settle Option A with one experiment.** Add `Set-Cookie` to the local
login response and observe whether subsequent `/gd/*` requests carry a `Cookie`
header. A single emulator run answers it. Either result is worth recording: a
positive closes an open item in `session_auth_lifecycle.md` and selects the
faithful design; a negative rules it out permanently and selects Option B.

**Step 2 — introduce an explicit session layer.** Replace the `otk`-keyed token
map and the single active-account marker with a session map keyed by the chosen
discriminator, established at signup and login where `uuid` is actually
present. Keep `otk` for response signing only; that use is correct, because a
shared per-window value is exactly what signing needs.

**Step 3 — define the unroutable-request policy explicitly.** A request that
arrives with no resolvable session — cold app start before login, dropped
cookie, changed address — must return a clean unauthorized response that sends
the client back to login. It must never guess an owner. This case is the one
the current single-account fallbacks exist to smooth over, and multi-account
operation makes guessing actively harmful: a wrong guess writes one player's
progress into another player's save.

**Step 4 — audit isolation.** Per-account request-replay caches are already
stored under each account, which is correct; confirm no shared cache, counter,
or derived catalog state crosses accounts. Confirm the client-generated `uuid`
is genuinely distinct per device and install, since a collision would silently
merge two saves.

**Step 5 — measure rather than redesign concurrency.** Every mutation takes one
global state lock, and each mutation rewrites the whole state file. Both are
likely fine at household scale and should be measured under a real multi-device
test before being changed. Concurrent first-run resource downloads are the more
plausible bottleneck.

**Step 6 — extend guided setup.** Support installing to several devices against
one server, or naming per-player data directories. This depends on the physical
device path, since family devices are real hardware rather than emulators.

## 6. Certification

Two devices, two accounts, played simultaneously, proving:

- independent progress and independent wallets;
- correct replay when each client retries its own request;
- correct resumption after a server restart;
- correct resumption after each app is force-stopped and relaunched;
- an unroutable request returning a clean unauthorized response rather than
  being attached to the wrong account.

## 7. Explicit non-goals

No friends, PvP, co-op, raids, shared HP, ranking, or any social feature. No
account migration between devices. No remote or internet-facing exposure: this
remains a local-network server.
