# Run only the server on a separate Linux machine

Use this path when the APK will be prepared and installed from one computer but
the compatibility server and resources should remain on an always-on Linux
machine. **This is optional.** If you are setting up for the first time, use the
single-machine path in the [README](../README.md) instead.

The server machine needs:

- Python 3.11 or newer and this source checkout;
- the matching Android resource tree;
- your own copy of the APK, beside that resource tree;
- a stable address that the client device can reach; and
- an unused TCP port allowed by the machine's firewall.

It does **not** need the Android SDK, ADB, Java, a signing key, an emulator, or a
connected Android device: this host never prepares a client. Its local input
layout is:

```text
local-input/
  YOUR-CLIENT.apk
  resources/
    data_u2017/
      android/
        BG/
        Scenario/
        ...other resource categories...
user-data/
```

**Why the APK is on this machine too.** Four of the catalogs the complete game
needs are derived from it, and this host derives its own rather than waiting for
copies from the machine that builds the client. That copy step is the one
operators skip, and skipping it is close to invisible: the server starts, serves
the story, and then refuses an ordinary Companion equip with a reply the client
shows as a Network Error. Nothing is *sent* anywhere — the file is read locally,
exactly as guided setup reads it.

A host that genuinely cannot hold the APK still works; see [If this host cannot
derive its own catalogs](#if-this-host-cannot-derive-its-own-catalogs).

The examples below use port `8642`. Choose another port if necessary, but use
that same port everywhere and keep it to four digits or fewer for the legacy
client patch.

## Validate and run it in the foreground

From the repository root:

```sh
python3 -m liminal_gate.server_setup --port 8642 --prepare-only
python3 -m liminal_gate.server_setup --port 8642
```

The first command validates and hashes the resources without opening a socket.
The second rebuilds the manifest, enables the standard bundled policies, listens
on all network interfaces, and runs in the foreground. Account state, request
diagnostics, and generated manifests remain beneath `user-data/`. Press Control-C
to stop it.

From another machine on the trusted network, verify the listener by replacing
`SERVER_ADDRESS` with the server's address:

```sh
curl --fail http://SERVER_ADDRESS:8642/en/news/app
```

## Prepare the APK on the other computer

The client-preparation computer still needs its own APK, matching resources,
Android Build Tools, and Java. Build without installing or starting a second
server by passing the dedicated server's stable address:

```sh
python3 -m liminal_gate.tester_setup \
  --device-host 192.168.1.10 \
  --port 8642 \
  --prepare-only
```

Replace `192.168.1.10` with the dedicated server's reserved LAN address. Install
the resulting `user-data/liminal-gate-test.apk` on the intended device. The
address and port are compiled into that APK; changing either later requires
preparing and reinstalling it again.

## Back up the signing key before you need it

Copy `user-data/liminal-gate-test.keystore` and `user-data/keystore-password.txt`
off the APK workstation and keep them. Everything else that machine generates
can be rebuilt; these two cannot.

Android only lets an APK install over an existing one when both were signed with
the same key, so every later rebuild has to use this keystore. Without it the
install fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, and the only way
forward is uninstalling the app — which clears its data, gives the client a new
device UUID, and leaves your progress on the server under the old one. That is
recoverable, with [`adopt`](saves.md#if-you-reinstall-the-app-and-your-progress-is-gone),
but it is entirely avoidable.

The practical rule: always rebuild the APK on the same machine, from the same
`user-data/` directory.

## Updating

Most releases change only the server. The APK carries the client patches and the
one server address compiled into it; the bundled policies, catalogs, settlement
rules, and event flags all live on the server side, so they arrive with a pull
and a restart:

```sh
sudo systemctl stop project-liminal-gate
cd /opt/project-liminal-gate && git pull --ff-only
sudo systemctl start project-liminal-gate
```

**Your save is never involved.** `bootstrap-state.json` is written only by the
running server. Updating does not read or rewrite it, and neither does preparing
an APK on another machine — `tester_setup` writes build output and nothing else,
so there is no state to sync between the two computers in either direction.

Three things a pull and a restart do **not** do:

| What | When it matters | What to do |
| --- | --- | --- |
| Rebuild the APK | A release changes the client patch plan — an Android compatibility fix, for instance | Rebuild and reinstall from the APK workstation, with the same keystore. The changelog entry says when a release needs this. |
| Change the address or port | You move the server or pick a different port | Both are compiled into the APK, so rebuild and reinstall |
| Regenerate the derived catalogs | A release changes one of the *generators* rather than the server | Restart once with `--rederive-catalogs`; nothing is copied between machines |

The server refreshes `resources.json` from the resource tree on every start, so
that one needs nothing. The four derived catalogs are keyed to the APK they came
from, so an ordinary restart reuses them and only a changed APK re-derives them.
A corrected *generator* leaves the APK alone and therefore leaves them looking
current, which is what `--rederive-catalogs` is for:

```sh
sudo systemctl stop project-liminal-gate
cd /opt/project-liminal-gate && git pull --ff-only
python3 -m liminal_gate.server_setup --port 8642 --rederive-catalogs --prepare-only
sudo systemctl start project-liminal-gate
```

The changelog entry for that release says when this is needed; when it says
server-only, a pull and a restart are genuinely all of it.

If you are unsure whether an update needs more than a restart, the changelog for
that release states which. When it says server-only, a restart is genuinely all
of it.

## What this host generates

Everything it needs, from your own APK and resource tree: the resource manifest,
the tuning document, both banner families — the Pact artwork and the Attack of
Coin Creeps cards, neither of which the archive retained in the form the client
asks for — and these four catalogs:

| Catalog | Without it |
| --- | --- |
| `story-outcomes.json` | every story Companion the client rolls is discarded |
| `companion-equipment.json` | a newly equipped or retargeted Companion is refused |
| `event-catalog.json` | Archive Special Quests, Tower, and solo Eidolon quests are absent |
| `character-catalog.json` | Pact class rates and duplicate gains fall back to uniform |

**There is nothing to copy from the APK workstation.** The two machines each read
the same APK and each derive what they need from it: one builds a client, this
one serves it.

The first start that sees a new APK does the derivation, which takes several
minutes — it disassembles every chapter's battle program. Each catalog records
the APK it came from, so every later start finds them current and begins
immediately. Replacing the APK with a different build is what makes them stale,
and the next start derives again.

Deriving needs three tools that the client-facing half does not: UnityPy,
Il2CppDumper with a .NET runtime, and a disassembler that understands AArch64.
Install whatever is missing with:

```sh
python3 -m liminal_gate.doctor --install-missing
```

### Reading the drop reference this host generates

Alongside the four catalogs it writes `user-data/drop-compendium.html`: which
stages yield a given item or Companion, at the rates the recovered tables state.
It is self-contained, so opening that file is always the simplest route.

The server also serves it, to anyone it already serves the game to — so a
tester reads it on the same phone they play on, at the same address the client
is pointed at:

```
http://SERVER_LAN_ADDRESS:PORT/local/compendium
```

From this host itself, `http://127.0.0.1:PORT/local/compendium`. Two things
behave the way they do on purpose:

- **It is as reachable as the game is, and no more.** The page is derived from
  the same APK those clients are running, and this host already answers them
  every resource and catalog-backed request the game makes; withholding a
  reference to a game while serving the game would draw the line where nothing
  rests. The route is read-only. It is still a private-network setup, so the
  standing rule holds: do not port-forward this server.
- **`https://` fails misleadingly.** There is no certificate here, so a browser
  negotiating TLS reports *"This site can't provide a secure connection"* rather
  than anything about the route. Type the scheme instead of letting the address
  bar guess it.

The save (`/local/state`) and the event log (`/local/events`) are not like this
and stay loopback-only: they describe a person, and one of them is writable.

A host set up before this page existed reports its catalogs current and has no
page to serve, since the APK never changed — only the generator did. Starting it
once more writes the page from documents it already holds. If it instead prints
that it could not build one, `--rederive-catalogs` runs the full pass.

### If this host cannot derive its own catalogs

It still starts and still serves the story. What it cannot do is the rest of the
game, so the shortfall is reported at every start rather than left to be
discovered as a Network Error mid-play: the reason the derivation did not happen,
then one line per catalog naming what a player loses without it.

Two ways to run a host like that deliberately:

- Generate the four with [guided setup](../README.md#5-run-the-setup-command) on
  the APK workstation and copy them into this host's `user-data/`. They are
  ordinary files and the server does not care which machine produced them.
- Pass `--no-derive-catalogs` so this host never attempts derivation and uses
  whatever copies its data directory already holds.

## Keep the server running with systemd

On a Linux distribution that uses systemd, the included installer renders the
unit for the current checkout, current user, and selected port. It verifies,
installs, enables, and starts the service, prompting for sudo only for the
system-level operations. Keep the checkout in a path without spaces:

```sh
./scripts/install_systemd_service.sh 8642
```

The stamina meter is off on every launcher: the bar reads full and quest entry
never waits on it. To run this host with the retired service's timer gate
instead, add the flag, which the installer writes into the unit's `ExecStart`:

```sh
./scripts/install_systemd_service.sh 8642 --enable-stamina
```

Changing your mind means rerunning the installer with or without the flag; the
unit is the only place a systemd host passes a launcher option. See
[The stamina meter is off by default](advanced-configuration.md#the-stamina-meter-is-off-by-default).

### Tuning rates and gates on a running host

Rates are the exception to the rule above: they need no reinstall. Setup wrote
`user-data/tuning.toml` with every option in it, commented out, and this
launcher reads it on start — so changing a Pact rate, a Hunting unlock, or a
party gate is an edit and a restart:

```sh
$EDITOR user-data/tuning.toml
sudo systemctl restart project-liminal-gate.service
```

Uncomment only what you want to change; every line left commented keeps
following its bundled default, including through a later update that corrects
one. For example, to open all Hunting tiers at once and let any party onto the
two Roads:

```toml
[hunting]
tier_unlock_chapters = [1, 1, 1]

[gates]
species_limits = false
```

Keeping the file somewhere else takes `--tuning=PATH` at install time. The full
option list is [Tuning rates, gates, and
EXP](advanced-configuration.md#tuning-rates-gates-and-exp); a misspelled key is
refused at startup rather than silently ignored, so check `journalctl` after a
restart if the server does not come back.

The service runs as the invoking non-root user, restarts after an unexpected
exit, and starts during normal multi-user boot. Its systemd protections leave
only this checkout's `user-data/` writable. The invoking user must therefore be
able to read the source and resource tree and write `user-data/`.

Common operations:

```sh
systemctl status project-liminal-gate.service
journalctl -u project-liminal-gate.service -f
sudo systemctl restart project-liminal-gate.service
sudo systemctl stop project-liminal-gate.service
sudo systemctl start project-liminal-gate.service
```

After updating the checkout, restart the service to load the new code. Rerun the
installer instead when the checkout path, service user, or port changes.

To remove only the systemd integration while preserving resources and account
state:

```sh
sudo systemctl disable --now project-liminal-gate.service
sudo rm /etc/systemd/system/project-liminal-gate.service
sudo systemctl daemon-reload
```

## Optional access away from home

Do not port-forward this plain-HTTP preservation service or expose it directly to
the public Internet. A private overlay network is the safer remote-access
boundary.

One APK can use direct Wi-Fi at home and Tailscale while away if the server is
configured as a [Tailscale subnet router](https://tailscale.com/kb/1019/subnets).
Advertise the home subnet, keep the APK pointed at the server's reserved LAN
address, and connect the client device to Tailscale only while away. Subnet
routing, route approval, firewall rules, and tailnet access controls are
network-administration steps outside this project.
