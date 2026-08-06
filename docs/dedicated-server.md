# Run only the server on a separate Linux machine

Use this path when the APK will be prepared and installed from one computer but
the compatibility server and resources should remain on an always-on Linux
machine. **This is optional.** If you are setting up for the first time, use the
single-machine path in the [README](../README.md) instead.

The server machine needs:

- Python 3.11 or newer and this source checkout;
- the matching Android resource tree;
- a stable address that the client device can reach; and
- an unused TCP port allowed by the machine's firewall.

It does **not** need the APK, Android SDK, ADB, Java, a signing key, an emulator,
or a connected Android device. Its local input layout is:

```text
local-input/
  resources/
    data_u2017/
      android/
        BG/
        Scenario/
        ...other resource categories...
user-data/
```

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
| Regenerate the derived catalogs | A release changes one of the *generators* rather than the server | Rerun guided setup on the APK workstation and copy the refreshed files over; see the next section |

The server does refresh `resources.json` from the resource tree on every start,
so that one needs nothing. `story-outcomes.json`, `event-catalog.json`,
`character-catalog.json`, and `companion-equipment.json` are derived once and
then read as they are, which is why a generator change needs the extra step.

If you are unsure whether an update needs more than a restart, the changelog for
that release states which. When it says server-only, a restart is genuinely all
of it.

## Which generated files the server machine needs

Retain the matching resource tree, `resources.json`, `story-outcomes.json`,
`event-catalog.json`, `character-catalog.json`, `companion-equipment.json`,
optional `public_data/`, and the server's durable `bootstrap-state.json`. Keep
the remaining generated output on the setup workstation.

If the dedicated host predates one of these generated runtime catalogs, rerun
guided setup on the APK workstation and copy the matching generated files into
the dedicated server's `user-data/` directory before updating the server. See
[What setup generates](generated-files.md).

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
