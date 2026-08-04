# Run the server inside the Android APK

This is the self-hosted setup: one private APK contains the reviewed Terra
Battle client, the compatibility server, and your matching resource tree. When
you open the app, it starts the server on Android loopback and waits for a
matching health response before starting Unity. You do not keep a Python server
running on another computer, choose a port, or configure Wi-Fi routing.

Status: the build, package, loopback service, one exact resource response, and
force-stop/relaunch path have passed on an API 34 ARM64 emulator. Installation
and gameplay with the final source-exact artifact on physical ARM64 hardware,
an ARMv7 runtime, and through Chapter 2-1 are still pending. Treat this as a
private testing path, not a completed physical-device certification.

## Before you start

You need:

- a physical Android device or emulator running API 24 or newer;
- an `arm64-v8a` or `armeabi-v7a` runtime;
- USB debugging and enough USB access for `adb devices -l` to show `device`;
- at least 4 GiB free in the device's `/data` partition;
- several GiB of temporary space on the build computer;
- your own Terra Battle Android 5.5.7-170 APK and matching Android resources;
- this complete source checkout, including `android-host/`.

The reviewed source APK must have SHA-256
`f2c0ffa188255f4694f0f60e898a58b372c2cc3fff7dd312a01d593189bd7a15`.
Setup refuses a different APK instead of guessing that its binary layout is
compatible. Do not commit, upload, or redistribute the generated APK, resource
tree, signing key, or save.

Run every command below from the project folder containing `README.md`,
`liminal_gate/`, and `android-host/`.

The examples use a Unix shell and `python3`. In PowerShell, use `py -3`, replace
a trailing `\` with a backtick, use `New-Item -ItemType Directory -Force` for
`mkdir -p`, and use `Copy-Item` for `cp`.

One exception, and it is the one that misleads: after step 2 activates the
virtual environment, use plain `python` rather than `py -3`. Naming a version
makes the launcher skip the active environment, so `py -3` from a `(.venv)`
prompt runs the system Python instead.

## 1. Put your private inputs in place

The default paths are:

```text
local-input/
  terra-battle-5.5.7-170.apk
  resources/
    data_u2017/
      android/
        BG/
        Scenario/
        ...other resource categories...
user-data/
android-host/
```

Create the private directories if needed:

```sh
mkdir -p local-input/resources/data_u2017/android user-data
```

The resource root is the final `android/` directory whose immediate children
include categories such as `BG`, `Scenario`, and `Pieces`. If your inputs live
elsewhere, keep them there and pass `--apk` and `--resource-root` to both the
check and the real command.

## 2. Install and check the build tools

Using a virtual environment avoids system-Python package restrictions:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

In PowerShell, that is two commands as well. Run the first, wait for it to
finish, then run the second:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

The prompt shows `(.venv)` once the environment is active. Keep that window
open: the remaining commands need it.

**From here on, `py -3` is the wrong command.** `py -3 -m venv` above was
correct — there was no environment yet — but once `(.venv)` is showing, spelling
out a version makes the launcher skip the environment and run the system Python.
Anything installed that way lands where `.venv` cannot see it, and the checks
below then report it missing. Use plain `python -m`, or
`.\.venv\Scripts\python.exe -m`.

**If activation is refused** with `running scripts is disabled on this system`,
you do not have to change any policy. Activation is a convenience; naming the
environment's own interpreter does the same thing, because setup installs
packages with the interpreter running it rather than whatever `pip` is on
`PATH`. Use this in place of every `python3` below and skip activation
entirely:

```powershell
.\.venv\Scripts\python.exe -m liminal_gate.doctor --install-missing
```

If you would rather activate, relax the policy for the current window only —
no administrator, nothing persisted:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

`-Scope CurrentUser RemoteSigned` makes it persistent for your account. Should
either be ignored, a policy set by your organization outranks it;
`Get-ExecutionPolicy -List` names the scope that is winning, and that one needs
an administrator. Reach for `Unrestricted` last: it is broader than this needs.

Let the project inspect the toolchain and install what it safely can:

```sh
python3 -m liminal_gate.doctor --install-missing
```

Vendor tools and their recorded locations stay under ignored `user-data/`;
required Python packages install into the active virtual environment. The
doctor asks before accepting Android SDK licences. If no installed tool can
read AArch64, it adds Google's pinned side-by-side NDK and records that
package's `llvm-objdump`; it does not install Android Studio. Keep this
environment active for the remaining commands. See
[Installing the tools](install-tools.md) for manual and platform-specific
alternatives.

Now run the non-mutating check with the exact device you intend to use:

```sh
adb devices -l
python3 -m liminal_gate.on_device_setup --check --device YOUR_ADB_SERIAL
```

The serial is the first column in `adb devices -l`. Accept the USB-debugging
prompt on the device if it says `unauthorized`. Fix every `FAIL` before
continuing. A missing Gradle cache is only a warning: the real command downloads
the pinned, checksum-verified Gradle 8.11.1 distribution into `user-data/work/`.

When using non-default inputs, repeat them exactly:

```sh
python3 -m liminal_gate.on_device_setup --check \
  --device YOUR_ADB_SERIAL \
  --apk /path/to/terra-battle-5.5.7-170.apk \
  --resource-root /path/to/data_u2017/android
```

## 3. Build, install, and launch

With the default file layout:

```sh
python3 -m liminal_gate.on_device_setup --device YOUR_ADB_SERIAL
```

This one command:

1. validates the immutable source APK and resources;
2. derives all catalogs required by the supported local game;
3. patches API and resource traffic to fixed `127.0.0.1:8002`;
4. builds the dual-ABI embedded Python host;
5. packages the complete resource tree without a second extracted device copy;
6. signs `user-data/on-device-liminal-gate.apk` with the checkout's local key;
7. installs it with ADB incremental installation disabled; and
8. launches the exact replacement activity.

The first build is substantial: the validated retained tree produced a roughly
1.0-GiB APK. Leave the device connected and do not interrupt the command while
it is signing or installing. The command succeeds only after printing both:

```text
Prepared private on-device APK: user-data/on-device-liminal-gate.apk
Installed and launched on YOUR_ADB_SERIAL. The embedded server binds only to 127.0.0.1:8002.
```

To build without changing a device, use:

```sh
python3 -m liminal_gate.on_device_setup --prepare-only
```

## 4. Verify startup and play

The app briefly shows **Starting local service…**. Unity appears only after the
embedded server answers `/healthz` with the build ID compiled into that same
package. Once the game appears, the setup process on the computer may exit; no
separate server terminal or LAN address is needed.

Complete the normal client flow:

1. Title screen → New Game → tutorial summons and party steps.
2. Complete Borderlands 1-1 through 1-5.
3. On World Map, select `Ch 2: To the Capital` and complete section 1.
4. Confirm section 2 is marked **New** and World Map shows **210 Coins**.
5. Force-stop the app, reopen it from the launcher, and confirm the same
   progress and Coin display return.

That last restart is important: reopening the app starts a new embedded service
with the existing app-private state. A successful build or health screen alone
does not prove gameplay or persistence.

## Protect the on-device save

The combined APK keeps its server state and replay records in the app's private
files directory. Copy that state to this computer before you rely on it:

```sh
python3 -m liminal_gate.on_device_state export --device YOUR_ADB_SERIAL
```

The app must be open and past the loading screen; the export reads the running
server over USB and changes nothing on the device. See
[The on-device save](saves.md#the-on-device-save) for `import` and `update`.

Updating an install with another build from the same checkout normally uses the
same local signing key and preserves app data. Do **not** uninstall the app,
clear its storage in Android settings, or use `--replace-existing` after you
have progress you care about. Those paths destroy the on-device save, and
restoring an export onto a cleared install additionally requires re-pointing it
at the client's newly generated UUID. Preserve the checkout's local signing key
too: losing it does not erase the installed save immediately, but it prevents a
future build from updating that install in place.

An export is also the answer to a save the app will not load. The state
document has no schema version and no migration step, so a future revision that
changes its shape can leave a perfectly intact save unreadable — and the
retained `.bak.N` copies beside it are inside app-private storage, where the
recovery advice the server prints cannot be carried out. An export taken while
the old build still ran is the copy that survives that.

Advanced users can seed a *new* install from an existing workstation-hosted
server state before the app has created any state of its own. Stop the
separate server first, then:

```sh
cp user-data/bootstrap-state.json user-data/seed-state.json
python3 -m liminal_gate.on_device_setup --device YOUR_ADB_SERIAL --seed-state
```

`--seed-state` reads exactly `<data-dir>/seed-state.json`, embeds that private
file in the generated APK, and copies it only when `state.json` does not already
exist on the device. It never overwrites an existing on-device save. This seeds
the server document; it does not change the Android client's device UUID or
guarantee that an account created on another device becomes active. Test a
migration on a disposable install before relying on it. A seeded APK contains
the save, so protect it as carefully as the save itself and never share or
commit it.

## Rebuild or update

Pull the desired source revision, then rerun the same command with the same
`--data-dir`. The local signing key under `user-data/` lets Android update the
package in place, and the existing on-device save remains in app data.

If Android reports a signature mismatch, stop before using
`--replace-existing`. That flag uninstalls the current app and clears its private
state. It is appropriate only for a disposable install or a device with no save
you need. See [On-device APK troubleshooting](troubleshooting.md#on-device-apk).

## What stays private

The build computer retains the signing key, derived catalogs, Gradle cache,
staging files, and `user-data/on-device-liminal-gate.apk`. Android retains the
installed package and app-private state. [What setup generates](generated-files.md)
explains which workstation files are reproducible and which must be preserved.

For implementation and validation evidence rather than operator steps, see
[Private on-device compatibility server](on-device-server-idea.md).
