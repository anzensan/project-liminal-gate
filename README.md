# Project Liminal Gate

Project Liminal Gate is a local compatibility server for a playable preservation
path. You run it on your own computer, point your own copy of the game at it, and
play offline on an Android emulator or a physical phone or tablet.

☕ If you find this project helpful, consider [buying me a coffee!](https://buymeacoffee.com/anzensan).
Donations support independent clean-room development and project operating costs.

> **Support policy:** contributions are voluntary and non-refundable. They do not
> purchase software, access, support, features, priority, or rights in Terra
> Battle or any original game material; this project remains source-only and
> separately licensed.

## What you can play

The guided setup enables ordinary story progression through **Chapter 42**, local
Pacts, Companion draws, job unlocks, Rebirth, and status items.

**Chapter 9 is the verified evidence checkpoint**, played through on the original
client on physical hardware. Everything past it is a bulk compatibility policy,
not a claim that every later reward, drop, or scripted scene has been
historically reproduced. This is a tester build, and later stages may still need
individual fixes.

**Optional areas — Hunting, Metal Zone, Arena, Tower — open on story progress, so
most are locked on a new account. Empty optional screens at the start are expected,
not a fault.** Arena VS, rankings, and multiplayer are disabled.

Full detail: [What works right now](docs/scope-and-status.md).

## Before you start

### Tools you install

Install Python 3.11+ and provide either a USB-debuggable Android device or an
emulator. Step 1 installs and remembers the JDK, Android SDK tools, pinned
Android NDK AArch64 disassembler, Il2CppDumper, and its runtime. Android Studio
is only needed if you want its emulator GUI; a physical-device setup does not
need the IDE.

### Files you supply

A local Terra Battle Android **5.5.7-170** APK and its matching Android resources.

**This project does not provide download links or instructions for obtaining the
APK or resource pack.** They stay on your machine; this repository does not
include them, and neither should any copy you make of it.

## Setup

Run every command from the project folder — the one containing `README.md` and
`liminal_gate/`:

```sh
cd /path/to/project-liminal-gate
ls README.md liminal_gate
```

Do not run them from your home directory, from inside the `liminal_gate/`
subdirectory, or from another project.

### 1. Install the tools

Let the doctor do it. It reports what this machine is missing and, with
`--install-missing`, downloads the rest from each vendor into `user-data/`:

```sh
python3 -m liminal_gate.doctor --install-missing
```

It fetches a JDK, the Android SDK packages, the pinned Android NDK
`llvm-objdump`, and Il2CppDumper, then records where everything landed in
`user-data/toolchain.json`. **Setup reads that file, so you never have to set
`PATH` or `JAVA_HOME`** — in this terminal or any later one.

Two things it deliberately leaves to you:

- **The Android SDK licences.** It prints the agreement and asks; it will not
  accept Google's terms on your behalf. Answer `y`, or pass
  `--accept-android-sdk-licenses`.
- **An emulator.** You still need Android Studio, or a physical device, to have
  something to install onto.

Prefer to install everything yourself, or want to know what the doctor is doing?
**[Installing the tools](docs/install-tools.md)** covers each tool by hand, per
operating system.

### 2. Check your setup

This reports on every requirement and changes nothing:

```sh
python3 -m liminal_gate.tester_setup --check
```

Each line is either `ok`, `warn`, or `FAIL` with the command that fixes it. Fix
every `FAIL` before continuing. The `device` line is only a warning when no device
was selected, because you do not need an emulator running until you install.

Add the same `--apk`, `--resource-root`, `--data-dir`, `--port`, `--device`, and
`--device-host` options you intend to use for real, so the check validates the
exact paths the build will use.

### 3. Put your files in place

Create the workspace:

```sh
mkdir -p local-input/resources/data_u2017/android user-data
```

Then arrange your APK and resources like this:

```text
local-input/
  terra-battle-5.5.7-170.apk
  resources/
    data_u2017/
      android/
        BG/
        Scenario/
        ...other resource categories...
```

The important resource folder is the final `android/` directory — the one whose
immediate children are categories such as `BG`, `Scenario`, and `Pieces`. Setup
validates this before it modifies anything, and prints the path it selected. Do
not spell the folder `datau2017`; the underscore in `data_u2017` is required.

To locate files already on your computer:

```sh
find "$HOME/Downloads" "$HOME/Desktop" -name 'terra-battle-5.5.7-170.apk' -print 2>/dev/null
find "$HOME/Downloads" "$HOME/Desktop" -type d -path '*/data_u2017/android' -print 2>/dev/null
```

```powershell
Get-ChildItem "$HOME\Downloads", "$HOME\Desktop" -Recurse -File -Filter "terra-battle-5.5.7-170.apk" -ErrorAction SilentlyContinue
Get-ChildItem "$HOME\Downloads", "$HOME\Desktop" -Recurse -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like "*\data_u2017\android" }
```

### 4. Start an emulator

Create an Android emulator and note its serial. **Choose an Android 14 image with
Translated ABI support**, and start it with `-gpu swangle` — the two settings that
prevent the most common failures. See **[Emulator setup](docs/emulator.md)**.

```sh
adb devices -l
```

The first column of the emulator's line (`emulator-5570`) is the serial you need
next.

**Testing on a real phone or tablet instead?** Follow [Install on a physical
device](docs/device-setup.md) for steps 4 and 5, then come back for step 6. A
physical device is the better choice if you care about graphics or sound.

### 5. Run the setup command

Pick a free TCP port with **four digits or fewer** (the example is `8696`), then:

```sh
python3 -m liminal_gate.tester_setup --port 8696 --device emulator-5570
```

Replace the port and serial with yours. This one command validates your inputs,
recovers what it needs from your own APK, creates a local signing key, patches and
signs the APK, installs it on that one device, and starts the server in the
foreground. Press Control-C when you finish testing.

It takes a while on the first run, because it runs Il2CppDumper and a disassembler
over your APK to recover the data an IL2CPP build strips out. Without that, a story
clear cannot award a Companion. If a required tool is missing, setup says so in the
first few seconds and names the fix.

Optional, for the retired Pact banner images: [install the image-extraction
dependency](docs/install-tools.md#optional-the-python-image-extraction-dependency)
first. Pacts work without it.

Options for this command — `--data-dir`, `--prepare-only`, `--replace-existing`
and the rest — are in [Setup options](docs/setup-manual.md#guided-setup-options).

### 6. Play

With the server running, complete the normal client flow:

1. Title screen → New Game → tutorial summons and party steps.
2. Complete Borderlands 1-1 through 1-5.
3. On World Map, select `Ch 2: To the Capital` and complete section 1.
4. Confirm section 2 is marked **New** and World Map shows **210 Coins**.
5. Stop and relaunch the app with the same server state. Progress and the
   210-Coin display should resume.

Past that, ordinary story progression is enabled through Chapter 42.

The app data on the device and the server state file are a matched pair. To begin
another clean test without overwriting an earlier run, use another `--data-dir` and
clear this test app's data before choosing **New Game** again:

```sh
adb -s emulator-5556 shell pm list packages | grep -Ei 'terra|mist'
adb -s emulator-5556 shell pm clear YOUR_TERRA_BATTLE_PACKAGE
```

```powershell
adb -s emulator-5556 shell pm list packages | Select-String "terra|mist"
adb -s emulator-5556 shell pm clear YOUR_TERRA_BATTLE_PACKAGE
```

Replace `emulator-5556` with your own serial — a physical device serial works the
same way — and `YOUR_TERRA_BATTLE_PACKAGE` with the value shown by the first
command. This clears only that app's local data on that one target; it does not
remove the APK or affect anything else.

## Local-network safety

The guided server listens on all host interfaces because an emulator or physical
Android device must reach it. **It is not an Internet-facing service:** keep the
selected port behind your firewall and never forward it from a router.

Signup or login identifies a device before rotated tokens may mutate its save; an
unknown LAN host is refused rather than inheriting the active account. Resource
files explicitly listed in the local manifest remain readable to devices that can
reach the port, so use a trusted local network.

## If something goes wrong

Look up your symptom in **[Troubleshooting](docs/troubleshooting.md)** — it is
grouped by where you are, from tools setup through to graphics and sound.

If you hit a Network Error that it does not cover, please [open a GitHub
issue](https://github.com/anzensan/project-liminal-gate/issues) using the
**Network error** form, with the action you took, your OS and emulator or device
version, and the relevant lines from `user-data/events.jsonl`. Do not attach APKs,
resources, captures, account saves, tokens, digests, or keys.

## Documentation

**Setting up and playing**

- [Installing the tools](docs/install-tools.md) — prerequisites, per-OS setup, Il2CppDumper.
- [Emulator setup](docs/emulator.md) — creating an AVD, the black screen, sound.
- [Install on a physical device](docs/device-setup.md) — phones and tablets over Wi-Fi.
- [What works right now](docs/scope-and-status.md) — story, Pacts, and what stays locked.
- [Look after your save](docs/saves.md) — backups, the save editor, recovering progress.
- [Troubleshooting](docs/troubleshooting.md) — symptoms and fixes.

**Going further**

- [Setup options and manual setup](docs/setup-manual.md) — every option, and the individual commands.
- [Run only the server on a separate Linux machine](docs/dedicated-server.md) — dedicated server, systemd, remote access.
- [What setup generates](docs/generated-files.md) — every produced file and why it is kept.
- [Advanced local configuration](docs/advanced-configuration.md) — optional progression, outcome, inventory, Pact, and Companion catalogs.
- [Save editor](tools/save-editor.html) — a single local page; see [Editing a save](docs/saves.md#editing-a-save).

**Project and protocol**

- [Developer reference](docs/developer-reference.md) — server modes, custom profiles, resource serving, APK tools, release checks.
- [Rehearse setup before you trust a change](docs/setup-rehearsal.md) — one command that reruns the whole setup pipeline on a clean copy and compares it with a run you trusted.
- [Server protocol](docs/server-protocol.md) and [current checkpoint](docs/current-checkpoint.md) — transport, persistence, evidence labels, and the verified client boundary.
- [Reconstruction architecture](docs/reconstruction-architecture.md) and [distribution architecture](DISTRIBUTION_ARCHITECTURE.md) — runtime modules and the source-only public/private separation.
- [Compatibility scope](COMPATIBILITY_SCOPE.md) — supported operations and refusals.
- [Parity roadmap](PARITY_ROADMAP.md) — what is implemented, what is permanently unrecoverable, and what is still open.
- [Changelog](CHANGELOG.md) — what each release claims, and what it does not.
- [Contributing](CONTRIBUTING.md) — reporting network errors, and what never to attach.
