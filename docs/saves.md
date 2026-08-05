# Look after your save

Your progress lives in one file, `bootstrap-state.json`, inside the `--data-dir`
you chose at setup. Everything below needs the server **stopped** — it holds the
save while it runs, and these commands refuse to touch a save in use.

That description applies to the separate-computer server. The
[self-hosted single-APK route](on-device-setup.md) instead stores `state.json`
in Android app-private storage, which the commands on this page cannot open
directly. Move it to this computer first with
[`on_device_state`](#the-on-device-save); every command here then applies to
the exported copy, and `import` puts it back.

**Only one server may use a save at a time.** Two servers pointed at the same
`--data-dir` do not share it: each keeps the whole save in memory and rewrites all
of it, so the second silently overwrites the first player's progress. The server
now refuses to start rather than let that happen. If you run a second server — a
different port, a second player — give it its own `--data-dir`.

## Inspect, back up, restore

See what you have, including the states kept automatically before recent saves:

```bash
python3 -m liminal_gate.account_state inspect user-data/bootstrap-state.json
```

Keep a copy before doing anything risky, and go back to one if you need to:

```bash
python3 -m liminal_gate.account_state snapshot user-data/bootstrap-state.json
python3 -m liminal_gate.account_state restore \
  user-data/bootstrap-state.json \
  user-data/bootstrap-state.json.bak.1 --yes
```

Restoring keeps your current save alongside as a timestamped
`.pre-restore.*.json`, so a restore is itself undoable. If several safety copies
are made in the same second, each receives a distinct suffix rather than
overwriting an earlier copy.

## The on-device save

The self-hosted APK keeps its save inside the app, where no file on this
computer corresponds to it. `on_device_state` moves it across, over USB, while
the app is running — open the game and wait for it to appear first.

```bash
python3 -m liminal_gate.on_device_state export --device YOUR_ADB_SERIAL
```

That writes a full copy under `user-data/on-device-state/` and changes nothing
on the device. **Do this before a long playthrough, and before any update you
are unsure of.** Exports are never rotated or pruned, so old ones stay until you
remove them.

Everything else on this page works on that exported file. To put it back:

```bash
python3 -m liminal_gate.on_device_state import \
  --device YOUR_ADB_SERIAL user-data/on-device-state/YOUR-EXPORT.json --yes
```

`import` refuses a file that breaks the invariants the client relies on, and
refuses one missing an account the device currently holds — that is far more
often the wrong file than an intended deletion. `--force` overrides both. The
save being replaced is kept on the device as `state.json.bak.1`, and the app is
restarted and re-read to confirm the import took.

To rebuild and reinstall with the save backed up first:

```bash
python3 -m liminal_gate.on_device_state update --device YOUR_ADB_SERIAL
```

`update` exports before it builds, installs over the existing app, and then
confirms the accounts survived. It never uninstalls. If Android refuses the
install because the build is signed with a different local key, it stops and
prints the recovery steps rather than clearing the app itself.

`export` and `update` have both been run successfully against a physical Pixel
7 Pro on Android 15 from a Windows build host, on an install carrying real
gameplay progress. `import` has not had the same confirmation, which is another
reason to keep the export you took before you need it. See
[Known-good setups](on-device-setup.md#known-good-setups).

A build installed before this route existed cannot be exported, so the first
update onto one has no backup to take. `update` says so and stops; add
`--allow-missing-backup` to accept that one update. An in-place update keeps the
save on its own, and the build it installs can be exported afterwards.

**Restoring onto a cleared install needs one extra step.** The client generates
a new UUID whenever its data is cleared, so a restored save names an account
the app no longer asks for. Let the reinstalled app reach the title screen once,
export that fresh state to read its new account id, then re-point your real save
at it with [`adopt`](#if-you-reinstall-the-app-and-your-progress-is-gone) before
importing.

While the app is running, its save is readable and replaceable by any other app
on that device over loopback. That is the cost of there being any route in or
out at all; it is worth knowing before you install this build on a phone you use
for other things.

## Editing a save

`tools/save-editor.html` is a single file with no network access and no
dependencies: open it in a browser, load your save, change what you want, and
export. **Stop the server first** — it keeps the whole save in memory and rewrites
all of it when it persists, so an edit made while it runs is lost. A browser
cannot see the lock the server uses, so that check is yours.

Apply the exported file with the command the editor shows:

```bash
python3 -m liminal_gate.account_state apply user-data/bootstrap-state.json \
  edited-save.json --yes
```

That is the part that decides whether the edit is safe. It re-checks the file in
Python, refuses one that breaks something the client or server relies on, refuses
one that has lost an account, keeps a timestamped backup, and will not write while
a server holds the save. To see what it would say without changing anything:

```bash
python3 -m liminal_gate.account_state validate edited-save.json
```

**Edit through the tool rather than by hand in a text editor.** A save is not
plain data, and the two ways it usually breaks are invisible in the JSON: a
character's `jobLevels` is a *packed* number whose low bits are the level and
whose upper bits are its progression, so writing a plain `90` sets the level and
destroys everything else in the field; and several numbers must stay decimals,
because the client reads them with an accessor that fails on a whole number and
takes the whole response down with it. The editor handles both. A text editor will
not warn you about either, and the damage shows up later, somewhere else.

If a value you changed was one the server had already answered a request with, add
`--clear-replay-cache` so a repeat of that request cannot return the old answer.
This clears tutorial, achievement, message, and Trading Post mutation responses
together; it does not alter the edited account state itself.

Character, item, and Companion names appear beside their IDs when
`user-data/names.json` is present. Setup writes it if you pass `--dummy-dll-dir`,
decoding the names from your own copy of the game; see
[advanced-configuration.md](advanced-configuration.md). Without it everything
still works, just with bare ID numbers.

## If you reinstall the app and your progress is gone

Your account is keyed to an ID the app generates on first run. Clearing the app's
data or reinstalling gives it a new one, so it signs up as a new player while your
real save sits untouched in the same file. **Nothing is lost** — the save just
needs pointing at the new ID.

Run `inspect`, find your real account (the one with your character count and
coins) and the new empty one, then:

```bash
python3 -m liminal_gate.account_state adopt user-data/bootstrap-state.json \
  --from <your-old-account-id> --to <the-new-account-id> --yes
```

Start the server and launch the app; your progress is back. `adopt` refuses to
overwrite an account that has been played unless you add `--force`, and it
preserves the file first either way.

**Pick `--to` by which ID the app is sending now, not by which looks newest.** A
save collects an account per reinstall, and after a few of them none of the
candidates is recognisably empty. `inspect` marks the one that logged in most
recently `"active": true`, and its `clientHosts` is the address that client
reached the server from — your device's LAN address, or `127.0.0.1` for an
emulator or a phone forwarded with `adb reverse`. Launch the app once, run
`inspect` again, and the account that just became active is the one to adopt
onto. Getting this wrong points your save at an ID nothing sends, so the app
still shows a stranger's progress and the account you meant to keep is now the
one holding your save.

That is also what the played-account refusal is for: if `adopt` says the target
has its own progress, the answer is usually a different `--to`, not `--force`.
Reach for `--force` only once you know the account it names is one you want
gone.

## Two players on one server

Each device is routed by its own network address, so two phones or tablets on your
network can hold separate saves against one server. Two emulators on this same
machine cannot — they share one address and the server cannot tell them apart.
Give those a `--data-dir` and a port each instead.

## One account on two devices

The game never had a visible account system: the app silently generates its ID on
first run, so a second device always signs up as a new player. `link` is where
"log in to my account from another device" lives — it tells the server the second
device's ID belongs to your existing account.

Install and launch the game on the second device and let it reach the title
screen once, so it signs up. Stop the server, run `inspect`, and identify your
real account and the new empty one — if several devices signed up recently and
the empty accounts look alike, each entry's `clientHosts` shows the network
address it signed up from. Then:

```bash
python3 -m liminal_gate.account_state link user-data/bootstrap-state.json \
  --device <the-new-account-id> --to <your-account-id> --yes
```

Start the server again; both devices now open the same save. `inspect` lists the
linked IDs under the account's `linkedDevices`, `unlink --device <id> --yes`
detaches one again, and like `adopt`, `link` refuses to discard a played account
unless you add `--force` and preserves the file first either way.

**Play on one device at a time.** Linking shares the save; it does not merge
simultaneous play. Whichever linked device writes last wins, so finish on one
before picking up the other.
