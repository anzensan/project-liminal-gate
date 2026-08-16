# Play on an iPhone or iPad

The iOS client can reach this server, and it can share one save with an Android
device. It gets there by a different route than Android does, and that
difference explains everything else on this page.

The Android client is *patched*: setup rewrites the addresses inside it, so it
asks this server directly. The iOS client cannot be patched. Its executable is
FairPlay-encrypted, so nothing here can read or change the URLs compiled into
it, and it will only ever ask for the two hostnames the retired service used:

| Hostname | Port | Carries |
|---|---|---|
| `gdappserver.appspot.com` | 443, TLS | the game API |
| `storage.googleapis.com` | 80, cleartext | resources |

So the interception happens on the network instead. You point both names at
this server with a DNS rewrite, and a small front end answers them.

This works because the client validates no certificate at all — a self-signed
one is enough, and nothing needs to be trusted on the phone. That is a
statement about what this 2017 client does, not a recommendation.

**This is the dedicated-server route only.** The single-APK on-device package
is Android's, and has no iOS equivalent.

## What you need

- an unmodified iOS install of the client;
- your own extracted `data_u2017/iOS_2` resource tree;
- a DNS server you control that can rewrite names for one device — a router,
  Pi-hole, or AdGuard Home;
- a host for the server that can bind ports 80 and 443.

## 1. Put the iOS resources where the server looks

The iOS tree sits beside the Android one:

```
local-input/resources/data_u2017/
    android/     <- the Android client's resources
    iOS_2/       <- the iOS client's
```

`iOS_2` must hold the same nine categories as `android`: `BG`, `BGM`, `Banner`,
`BuddyImages`, `BuddyThumbs`, `Illust`, `Pieces`, `SE`, `Scenario`.

Nothing else is needed. Setup finds that directory on its own and serves it
alongside Android; if it is not there, you get an Android-only server exactly
as before. To keep it somewhere else, pass `--ios-resource-root`.

You should see this at startup:

```
Serving the iOS tree as well: 23594 URL(s) from .../data_u2017/iOS_2 under /gdresources/data_u2017/iOS_2/
```

Both clients are served by one server at the same time, because each asks on
its own URL base. **Do not merge the two trees.** The 32-hex prefix on a
resource filename hashes the asset's logical name rather than its contents, so
both trees spell every filename identically while holding different bundles —
merged, a client would receive the other platform's data.

## 2. Make a certificate

Any self-signed certificate works, since the client checks none:

```bash
mkdir -p user-data/ios
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout user-data/ios/gdappserver.key.pem \
  -out user-data/ios/gdappserver.pem \
  -subj "/CN=gdappserver.appspot.com"
```

## 3. Run the front end

It terminates TLS on 443, serves cleartext on 80, and relays both to the
server, which remains the only thing that decides anything:

```bash
python3 -m liminal_gate.ios_front_end \
  --upstream 127.0.0.1:8642 \
  --bind 192.168.1.10 \
  --certificate user-data/ios/gdappserver.pem \
  --key user-data/ios/gdappserver.key.pem
```

**Name your LAN address in `--bind`** rather than accepting the default. If
anything else on the host already holds 443 on another interface — Tailscale
does exactly this — binding every address fails while binding the LAN address
alone succeeds.

Ports 80 and 443 need privilege. Rather than running this as root, install it
as a service that is granted only `CAP_NET_BIND_SERVICE`; a template is in
`deploy/project-liminal-gate-ios.service.in`, and it is written to stop and
start with the server it relays to. A front end started by hand in a terminal
also dies with that terminal, which is a confusing way to lose a working setup.

## 4. Open the firewall

A default-deny firewall will drop this traffic, and the symptom is a loading
screen followed by `Network Error` with **nothing in any log**, because the
requests never arrive. On `ufw`:

```bash
sudo ufw allow from 192.168.0.0/16 to any port 80 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 443 proto tcp
```

Keep these scoped to your own network. These ports answer to Google hostnames;
they must never be reachable from the Internet.

## 5. Redirect the two hostnames

Point **both** `gdappserver.appspot.com` and `storage.googleapis.com` at the
server, scoped to the phone. They are two separate rules, and redirecting only
one gives a client that loads its artwork and then fails, or the reverse.

Scope matters: an unscoped `storage.googleapis.com` rewrite breaks every other
device on your network. In AdGuard Home this is a `$client` rule tied to the
phone's address — which means **it stops matching when the phone's IP
changes**, and that failure looks exactly like every other failure. If a setup
that used to work stops, check the phone's current address first.

## 6. First login

A brand-new install signs up and plays. An install that has talked to any
server before will go straight to login, and you will see:

```
GET /gd/login?uuid=...&titlelogin=True   401
{"error": "unknown_local_account"}
```

That means this server has never seen that device UUID. Do not try to force a
signup — link the device to an account instead, which is the same step used to
share a save.

## Sharing one save with an Android device

Both devices can play the same account, picking up where the other left off.
Take the UUID from the phone's failed login above, stop the server, and link it
to the account you want:

```bash
python3 -m liminal_gate.account_state snapshot user-data/bootstrap-state.json
python3 -m liminal_gate.account_state link user-data/bootstrap-state.json \
  --device 9F70C6AEFD40F2C2FCEC25213CE498AB \
  --to 382D02BAAC5BE6AD42FFDF6DA50D63F6 --yes
```

`inspect` lists your accounts and their ids, and shows `linkedDevices`
afterwards. The link both fixes the login and shares the save: a linked
device's UUID resolves to the shared account before any lookup happens, so it
survives even if the phone's app data is cleared and it signs up again.

Take the snapshot. Linking preserves its own `pre-link` copy, but the moment
worth protecting against is the phone's *first login* against an established
save, not the link itself.

**One device at a time.** This is handoff, not simultaneous play: each client
holds the whole save in memory and writes all of it back, so two devices on one
account at once will overwrite each other.

## When it does not work

Work from the front end's log, which records every request that arrives:

```bash
journalctl -u project-liminal-gate-ios -f
```

| What you see | Where the problem is |
|---|---|
| No requests at all | DNS. The rewrite is missing, or scoped to an address the phone no longer has. |
| Resources arrive, API does not | Only one of the two hostnames is redirected. |
| `401 unknown_local_account` on login | The device is not linked. See above. |
| `502` from the front end | The server behind it is not running. |
| Requests arrive and the phone still fails | A protocol problem. The log has the exact request. |

If nothing reaches the log at all, confirm the path without the phone:

```bash
curl -o /dev/null -w "%{http_code}\n" \
  "http://<server>/gdresources/data_u2017/iOS_2/BG/<a-file-in-your-tree>"
curl -k -o /dev/null -w "%{http_code}\n" "https://<server>/gd/get_current_time"
```

From another machine on the LAN those should answer `200` and `400` — the
`400` is correct, since that request carries no account token. If they work
from the server itself but not from another machine, it is the firewall.
