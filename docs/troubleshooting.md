# Troubleshooting

Find your symptom in the section that matches where you are. If a local
client-to-server request fails and nothing here covers it, see [Reporting a
network error](#reporting-a-network-error) at the end.

## On-device APK

This section applies to [the self-hosted single-APK route](on-device-setup.md).
It does not require a Python server on the computer, `--device-host`, a chosen
port, Wi-Fi routing, or firewall access.

| What you see | What to do |
| --- | --- |
| `--check` reports `Gradle cache` as `warn` | This is the one non-required build check. Run the normal command once while online; it downloads checksum-verified Gradle 8.11.1 below ignored `user-data/work/`. |
| The device check reports API below 24, no supported ABI, or less than 4 GiB free | Use an API 24+ device with `arm64-v8a` or `armeabi-v7a`, or free space before building. The full validated package is roughly 1.0 GiB and setup deliberately requires more installation headroom. |
| `on-device setup failed: Android host Gradle build failed` | Keep the complete trailing Gradle message. Rerun `python3 -m liminal_gate.on_device_setup --check --device YOUR_ADB_SERIAL`; confirm Android SDK Platform 35 and Java 17–23 are reported ready. The host source must exist at `android-host/` unless `--host-source` names another complete copy. |
| A large APK install appears successful but the package is absent | Update the checkout and use `liminal_gate.on_device_setup`; it forces ADB `--no-incremental` because incremental installation falsely reported success for the validated 1-GiB package. Do not substitute a manual incremental install. |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` or `signatures do not match` | The installed app and this checkout use different local signing keys. **Do not use `--replace-existing` if the installed app has progress you need:** uninstalling clears its app-private save. Export it first with `python3 -m liminal_gate.on_device_state export --device YOUR_ADB_SERIAL`, then restore it afterwards — a cleared install needs [`adopt`](saves.md#the-on-device-save) for the client's regenerated UUID. Otherwise use the original checkout/data directory and key. |
| The app stays at **Starting local service…** and then shows **Local service failed to start.** | Tap **Copy diagnostics**, preserve the copied text, then tap **Retry** once. The gate waits up to about 60 seconds for a matching loopback build ID. Do not start a LAN server; this package only uses `127.0.0.1:8002`. If retry fails, report the copied diagnostics and the exact setup command. |
| The app says **Unity player is unavailable in this package.** | The embedded server passed readiness, but the combined package does not contain the expected Unity player. Update the checkout, rerun the complete build from the reviewed source APK, and reinstall with the same signing key. Do not replace the launcher or assemble host/client APKs by hand. |
| The app closes instantly on launch, with `NoSuchMethodError` / `onServiceConnected` / `bitter.jnibridge` in the crash log | Rebuild with `--disable-google-services`. See [The app crashes instantly on recent Android](#the-app-crashes-instantly-on-recent-android) below; this affects both routes. |
| The game later shows Network Error | Force-stop and reopen the app so the embedded service starts in a new process. There is no computer-side server or changing LAN address to repair. If the startup gate fails, copy its diagnostics; if Unity starts and only a game action fails, report the last action and a privacy-reviewed log rather than guessing an endpoint response. |

The generated package is `user-data/on-device-liminal-gate.apk`. A successful
command prints both its path and `Installed and launched on ...`. See
[Protect the on-device save](on-device-setup.md#protect-the-on-device-save)
before uninstalling, clearing app storage, deleting a local signing key, or
using `--replace-existing`.

## Tools setup cannot find

| What you see | What to do |
| --- | --- |
| `No module named liminal_gate` | Run the command from the repository root: the folder containing `README.md` and `liminal_gate/`. |
| `keytool: command not found`, or `keytool is unavailable` | `keytool` comes with a JDK, not with the Android SDK, so adding the SDK to `PATH` does not provide it. Set `JAVA_HOME` to Android Studio's bundled runtime — on Windows `%LOCALAPPDATA%\Programs\Android Studio\jbr` — then reopen the terminal. Setup also searches that location itself, so do not copy `keytool.exe` into the project folder. See [Installing the tools](install-tools.md). |
| `adb is unavailable`, or `adb` is not found | Setup falls back to the SDK's own `platform-tools\adb`, so this means the SDK root was not found either. Set `ANDROID_SDK_ROOT`, or pass `--adb` with the full path to `adb`. Copying `adb.exe` into the project folder is not needed. |
| `APK signing failed: zipalign/apksigner is unavailable` | Set `BUILD_TOOLS` to one of the directories printed by `ls "$SDK_ROOT/build-tools"`; do not use the literal placeholder path from an older guide. On Windows see [if setup cannot find zipalign and apksigner](install-tools.md#if-setup-cannot-find-zipalign-and-apksigner). |
| `error: externally-managed-environment` from `pip install` | Your Python does not allow system-wide installs, which is normal for Homebrew Python. Use a virtual environment, then run setup from that same activated terminal. See [the optional Python dependency](install-tools.md#optional-the-python-image-extraction-dependency). |
| `guided derivations` is FAIL inside `(.venv)` but passes in a plain PowerShell window | The install went to a different interpreter than the check reads. `py -3` skips an active virtual environment, because naming a version makes the Windows launcher search installed Pythons instead, so `py -3 -m pip install ".[master-import]"` typed at a `(.venv)` prompt installs system-wide. Re-run the install with plain `python -m pip install ".[master-import]"`, or `.\.venv\Scripts\python.exe -m pip install ".[master-import]"`, from that same window. The check now prints the exact interpreter it read, which is the one to install into. |
| `disassembler` is missing | Run `python3 -m liminal_gate.doctor --install-missing`. After explicit Android SDK licence acceptance it installs pinned `ndk;27.3.13750724` under `user-data/toolchain/android-sdk/`, verifies that its `llvm-objdump` reports AArch64 support, and records the exact executable. The NDK is a large download; an already-working system `llvm-objdump` or `objdump` is reused instead. |

## Il2CppDumper

| What you see | What to do |
| --- | --- |
| `--check` says Il2CppDumper exists but could not start | A framework-dependent .NET apphost can exist while its runtime is undiscoverable. Install the .NET runtime, or point `LIMINAL_GATE_IL2CPPDUMPER` at the adjacent `Il2CppDumper.dll` instead; setup will run it through `dotnet`. |
| `--check` still cannot find Il2CppDumper after you installed it | Read the rest of that line: it distinguishes a variable that was never set from one naming a path that does not exist, a directory holding no release, or a `.dll` with no `dotnet` to run it. The two usual causes are a variable set in a different terminal window than the one running setup, and a path with a typo. Confirm with `Test-Path $env:LIMINAL_GATE_IL2CPPDUMPER` (PowerShell) or `ls "$LIMINAL_GATE_IL2CPPDUMPER"`. Copying the tool into this repository has no effect. |
| `--check` opens an Il2CppDumper file picker | Fixed; update your clone. The check used to run the tool with no arguments to see whether it starts, which is how the Windows release is asked to prompt for its inputs. It is now given arguments, so it cannot prompt. If you do run Il2CppDumper by hand, note that its first dialog wants `lib/arm64-v8a/libil2cpp.so` from your APK — not `Il2CppDumper.exe`, and not the 32-bit `armeabi-v7a` copy. |
| Setup reports `Cannot read keys when either application does not have a console` from Il2CppDumper | Fixed; update your clone. Il2CppDumper ends every run — including a successful one — with a "press any key to exit" it cannot perform while setup is capturing its output, so a complete dump used to be thrown away on the exit code that followed. Setup now judges the run by the `DummyDll` directory and `dump.cs` it produced. If those really are missing, read `user-data/il2cpp/il2cppdumper-last-run.log` for the actual fault, and you can set `"RequireAnyKey": false` in the `config.json` beside Il2CppDumper to remove the keypress entirely. |

## Building and signing the APK

| What you see | What to do |
| --- | --- |
| `legacy client plan generation failed: could not read the selected metadata member` | `--source-apk` must name the actual `.apk` file, not `local-input` or another directory. Guided setup selects the imported APK for you. |
| Input validation rejects the resource root | Use `local-input/resources/data_u2017/android`, not `local-input/resources`. |
| The signing command exits without output | Update an older checkout with `git pull --ff-only`, then rerun the command. A successful current version prints the signed APK path. |
| `tester setup failed: apksigner sign failed (exit code ...)` | Keep the complete message: current setup includes the Android signing tool's own error output after the exit code, without printing the password. That output distinguishes a keystore/password problem from a Build Tools or Java failure. |
| The keystore is never created, and setup reports it could not be created | The password was probably shorter than six characters, which `keytool` refuses. Setup now asks again rather than failing, states the minimum in the prompt, and repeats whatever `keytool` reported. If you are running the manual step instead, see [Create a local test signing key](setup-manual.md#2-create-a-local-test-signing-key). |
| `server origin ... allow at most 27` | The address and port do not fit in the space available inside the APK. Use a port with four digits or fewer, and an IP address rather than a host name. See [Choose a port](device-setup.md#d-choose-a-port-with-at-most-four-digits). |

## Choosing and reaching the separate-server target device

| What you see | What to do |
| --- | --- |
| `adb devices` shows no emulator | Start an emulator from Android Studio Device Manager, then run `adb devices` again. |
| `adb devices` does not list a connected phone or tablet | Enable USB debugging and accept the on-device authorization prompt; if still absent, try another USB cable, since charge-only cables carry no data. |
| `does not look like an emulator, and --device-host is still ...` | You are installing to a physical device but did not pass `--device-host`. Pass this machine's LAN address. If the target really is an emulator attached over TCP, pass `--device-host 10.0.2.2` explicitly. |
| `--device-host ... refers to the client's own device` | `localhost`, `127.0.0.1`, and `0.0.0.0` mean the phone or tablet itself. Use `10.0.2.2` for an emulator or this machine's LAN address for a device. |
| `--device-host must not contain a port` | Pass only the address in `--device-host` and set the port separately with `--port`. |

## Installing the APK

| What you see | What to do |
| --- | --- |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` / `signatures do not match` | For a self-hosted APK, stop: uninstalling also deletes its server save. Export it first with `python3 -m liminal_gate.on_device_state export --device YOUR_SERIAL`, then read [the on-device warning above](#on-device-apk); restoring afterwards needs [`adopt`](saves.md#the-on-device-save) for the client's regenerated UUID. For the separate-server layout, a build made with another checkout's local key is installed; rerun with `--replace-existing`, or uninstall it with `adb -s YOUR_SERIAL uninstall com.mistwalkercorp.guardians`. Either choice clears client app data, while the separate workstation server state remains in its `--data-dir`. |
| `INSTALL_FAILED_NO_MATCHING_ABIS` / `res=-113` | The emulator image has no ARM translation. Pick a **Translated ABI** image; see [Emulator setup](emulator.md#choose-an-android-14-image-with-translated-abi-support). |
| Android refuses to install the APK | Use a clean emulator profile or remove the differently signed prior test build. |

## Running the game

| What you see | What to do |
| --- | --- |
| Network Error before the title flow | On the self-hosted route, use [the on-device section](#on-device-apk). On the separate-server route, confirm the server uses `--host 0.0.0.0` and the same port embedded in the APK. If you change the port, rerun the plan, patch, sign, and install steps; then inspect `tail -n 20 user-data/events.jsonl`. |
| A device that worked yesterday now shows Network Error | This machine's network address probably changed. Recheck it, then rerun setup and reinstall. See [Keep that address from changing](device-setup.md#c-keep-that-address-from-changing). |
| The app closes at the title screen and logcat says `Using memoryadresses from more that 16GB of memory` followed by signal 11 | Fixed for the exact final client by the generated ARM64 plan. Run `git pull --ff-only`, rerun the complete setup command, and reinstall its new APK. `pip install ".[master-import]"` installs the current checkout; it does not pull newer source. Do not drop ARM64 on Pixel 7/7 Pro because those devices run 64-bit apps only. |
| `/gd/login` returns 401 or the title screen immediately shows Network Error after a server-state change | The emulator's saved account does not exist in the chosen server state file. Start with a new state-file name and clear the selected emulator app's data. |
| Resource-manifest error on server start | Confirm the resource root, then rerun `python3 -m liminal_gate.resource_catalog_builder`. |
| Attack of Coin Creeps is selectable but its card artwork is blank | Update the checkout, rerun the complete setup command, and reinstall the newly signed APK. The final retail catalog omitted `sp1003`, so a server restart alone cannot add the catalog record to an already installed client. Setup now derives a local Coin Creeps-family fallback from your retained resources. |
| `Pact banner preparation skipped: ... requires UnityPy` | Only the retired Pact banner images are missing; Pacts themselves work. Install the [optional dependency](install-tools.md#optional-the-python-image-extraction-dependency) if you want the images. |
| A request fails after Chapter 9 | Ordinary core-story progression is enabled, but a scripted reward/drop exception may still be unsupported. Record the route, chapter/section, steps, and sanitized event log. |
| Repeating Network Errors on a Strikes Back victory screen, with the reward items shown but never added | Fixed; update your clone and restart the server. A won Counter Descent battle reports its experience and drops, and the settlement had required the family to grant nothing, so it refused every real clear and the client retried a settlement it could never complete. Nothing is lost: the battle stays open, and re-entering the same stage after updating is treated as a retry that does not charge its stamina twice. |
| An optional area (Hunting, Arena, Tower) is empty or greyed out | Expected on a new account: these open on story progress. See [What works right now](scope-and-status.md#optional-areas-open-on-story-progress-so-most-are-locked-at-first). |

### The app crashes instantly on recent Android

The crash log names `NoSuchMethodError`, `onServiceConnected`, and
`bitter.jnibridge`, and the app closes before it reaches the title screen. The
server log shows no incoming connection, because the client never gets that far.

Rebuild with `--disable-google-services` and reinstall:

```sh
python3 -m liminal_gate.on_device_setup --device YOUR_ADB_SERIAL --disable-google-services
```

For the separate-server route, pass the same flag to
`python3 -m liminal_gate.tester_setup`. Both routes install the same client, so
both are affected.

**The combined APK survives this without the flag.** The host installs a
main-thread guard before Unity starts, which drops exactly this one callback and
keeps the app running. It is always on, logs each occurrence under the
`LiminalGate` tag, and passes every other error through untouched. It covers the
crash whatever caused the bind, which is why the self-hosted route was never
affected. The separate-server route has no host and so is not covered — use the
flag there.

**What the flag does.** The 2017 client's Unity bridge cannot dispatch an
interface method Android 16 added to `ServiceConnection`, and it fails the
moment a bind through that bridge completes. The flag rewrites the bind actions
so they resolve to nothing and the bind never completes: 18 in the client's
`classes.dex`, plus the one in Unity's own `libunity.so` that carries the crash,
in both ABIs. The store, Play Games, ads, Google auth, and Nearby are all
retired for this game; the last one costs Unity the advertising ID, which is
analytics for a service that no longer exists. Nothing you can use is lost.

**The `libunity.so` half was added after a Galaxy S26 crashed with the other 18
already applied.** Unity binds Play Services from native code to read the
advertising ID, using its own copy of the action string that no edit to the dex
can reach. Only Unity's connection is vulnerable at all: it is built as a
`java.lang.reflect.Proxy`, which routes an interface's `default` methods to its
handler instead of inheriting them, while every ordinary Java class in the
client inherits Android 16's new overload correctly. An earlier reading blamed
Google Play Billing; that is withdrawn, because billing's connection is an
ordinary class.

The flag is off by default because it edits client bytes no other supported path
touches and it is not yet confirmed on Android 16 hardware.

**Check whether your build actually has the flag before reporting that it did
not help.** The two routes are checked differently, and the difference matters:

| Route | How to check |
| --- | --- |
| On-device APK | The edit changes the build ID, so `/healthz` identifies which variant the install is running. Worth quoting in a bug report. |
| Separate server | `/healthz` cannot answer this — it is the workstation's own server and knows nothing about the installed client. Read the installed APK itself, with the two commands below. |

Do not read `user-data/local-server-plan.json` for this. It is rewritten by
every setup run, so it describes the last build rather than the installed one,
and the two disagree whenever a build succeeded but the install did not replace
what was already on the device. Pull the APK the device is actually running:

```sh
adb shell pm path com.mistwalkercorp.guardians    # note the base.apk path it prints
adb pull THAT_PATH installed.apk
python3 -c "import zipfile,sys;d=zipfile.ZipFile(sys.argv[1]).read('classes.dex');a=b'com.android.vending.billing.InAppBillingService.BIND';print('flag IS applied' if d.count(a)==0 else 'flag NOT applied')" installed.apk
```

A build made without the flag crashes exactly as an unpatched one does, because
it is one. If the check says the flag is applied and the app still crashes,
that is a new finding and the logcat is worth sending — it is how the
`libunity.so` half of the flag was found.

**To confirm the diagnosis before rebuilding**, disable Google Play Services in
Android's app settings and relaunch. If the game starts, this is the fault. That
is a heavy, device-wide change that affects your other apps; re-enable it once
you have a patched build.

## Graphics and sound

| What you see | What to do |
| --- | --- |
| Black screen after launching the app, no crash, server log shows `200` responses | The emulator's graphics backend cannot complete Unity's framebuffer. Restart the emulator from a terminal with `-gpu swangle`. Confirm with `adb logcat -d \| grep -c 0x506`: thousands of those errors mean graphics, not the server. See [Start the emulator with `-gpu swangle`](emulator.md#start-the-emulator-with--gpu-swangle-especially-on-macos). |
| No sound at all on an emulator | The emulator was probably created with audio output switched off. Add `hw.audioInput=yes` and `hw.audioOutput=yes` to the device's `config.ini`, then **cold boot** it — an ordinary restart can restore the silent device from a snapshot. See [Sound on the emulator](emulator.md#sound-on-the-emulator). |
| Sound starts on an emulator, then becomes silent after several seconds | An emulator/client compatibility failure, not the server. Paired captures rule out muting, rerouting, Android mixer underruns, and the earlier CPU-starvation theory; the old Unity/FMOD producer keeps feeding a fixed-power signal. A physical device is the only reliable workaround currently demonstrated. See [Sound on the emulator](emulator.md#sound-on-the-emulator). |
| Sound is distorted, cuts out, or does not return on a physical device | Check the [request log](#finding-the-request-log) for `404` requests beneath `/resources/SE/` or `/resources/BGM/`. A missing sound bundle in your local resource set can cause this; include those paths in the issue report. On an emulator, see the two rows above first. |

## Saves

| What you see | What to do |
| --- | --- |
| Progress is gone after reinstalling or clearing the app's data | For the self-hosted APK, app-private server state was cleared with it. Recovery needs an export taken beforehand — see [The on-device save](saves.md#the-on-device-save) — and that export must be re-pointed with `adopt` at the UUID the reinstalled client now generates. Without an earlier export there is no copy to recover. For the separate-server layout, the app generated a new account ID while the save remains in the workstation state file; see [If you reinstall the app and your progress is gone](saves.md#if-you-reinstall-the-app-and-your-progress-is-gone). |
| `local account state is already in use by another server` | Another server already has that save open. Stop it, or start this one with its own `--data-dir`. See [Look after your save](saves.md). |
| `account state is in use; stop the local server before changing it` | `restore` and `adopt` will not change a save a running server owns. Stop the server and run the command again. |

## Windows and PowerShell

| What you see | What to do |
| --- | --- |
| A `\` at the end of a line is rejected in PowerShell | The multi-line commands use a Unix shell convention. Use a backtick (`` ` ``) instead, or put the whole command on one line. [Manual setup](setup-manual.md#2-create-a-local-test-signing-key) gives PowerShell versions of both signing-key commands. |
| `Permission denied: 'user-data'` from `account_state` | Fixed; update your clone. Nothing was wrong with the folder or the save, and nothing was changed: publishing a save flushes the directory it was written into, which Windows refuses to open, and the refusal was treated as a failure. Every writing command — `adopt`, `restore`, `link`, `unlink`, `switch`, `apply` — stopped this way on Windows; `inspect`, `snapshot`, and `validate` were unaffected. |
| `running scripts is disabled on this system` when activating the virtual environment | You do not need to change any policy: activation only puts the environment's interpreter first on `PATH`, and naming it directly does the same job. Run `.\.venv\Scripts\python.exe -m liminal_gate.doctor --install-missing` and use that interpreter in place of `python3` from then on — setup installs packages with the interpreter running it, so they land in that environment either way. To activate instead, `Set-ExecutionPolicy -Scope Process Bypass` covers the current window only and needs no administrator; `-Scope CurrentUser RemoteSigned` persists for your account. |
| `Set-ExecutionPolicy` appears to succeed but activation is still refused | A policy set by your organization outranks the scope you changed. `Get-ExecutionPolicy -List` prints every scope and the one in force; `MachinePolicy` or `UserPolicy` there can only be changed by an administrator. Use the `python.exe` form above instead — it needs no policy at all. Setting `Unrestricted` machine-wide works but is broader than this task warrants. |
| The virtual environment commands look like one line | They are two: `py -3 -m venv .venv` creates it, `.\.venv\Scripts\Activate.ps1` activates it. Run them one after the other. The prompt shows `(.venv)` when it worked, and the remaining setup commands need that same window. |
| A package installs successfully but the next command cannot find it | Stop using `py -3` once `(.venv)` is showing. The launcher honours an active environment only when no version is spelled out, so `py -3` runs the system Python and installs there, while every later command reads `.venv`. Use plain `python -m`, or `.\.venv\Scripts\python.exe -m`. `py -3 -m venv .venv` was correct — there was no environment yet. |
| A command that starts with `$env:` is not recognized | PowerShell will not run a program named by a variable that way. Either `cd` to the folder first and use `.\name.exe`, or call it with `&`: `& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" devices`. |
| The prompt becomes `>>` and pressing Enter only adds a blank line | PowerShell thinks the line is unfinished, almost always because a quote was turned into a curly `"` in transit. Press Control-C to get back to the normal prompt and retype the command with straight quotes, or use a form that needs no quotes at all. |
| `grep` is not recognized in PowerShell | `grep` is a Unix tool. Use `Select-String` with the same pattern: `adb logcat -d \| Select-String "OpenSLES\|AudioTrack"`. When a filter is the problem rather than the point, capture the whole log with `adb logcat -d > full-log.txt` and attach that instead. |

## Reporting a network error

For a local client-to-server failure, open the GitHub **Network error** issue form
with the setup commands, client actions, last screen reached, expected result,
actual result, and a sanitized request-log excerpt.

**Do not attach APKs, resources, captures, account saves, tokens, digests, or
keys.**

### Finding the request log

The log records one line per request with its method, path, status, and time,
and refusals appear there as a `4xx` or `5xx` status. Where it lives depends on
which layout you run, and the two are not interchangeable:

| Layout | Where the log is | How to read it |
| --- | --- | --- |
| Separate server (workstation serves the device) | `user-data/events.jsonl`, beside the rest of your tester files | Read it on the workstation, not the device. PowerShell: `Get-Content user-data\events.jsonl -Tail 100 \| Select-String '"status":(4\|5)'` |
| On-device APK (the app hosts its own server) | The app's private storage, `files/events.jsonl` — there is **no** `user-data` folder on the device | `adb shell run-as com.mistwalkercorp.guardians cat files/events.jsonl > events.jsonl`, then filter it on the workstation |

`run-as` reads app-private storage without root, and works because the
self-hosted build is debuggable. If it refuses, `adb logcat` still shows the
Python server's own output for the same run.

A `Get-Content user-data\...` command run on the device, in a terminal
emulator, finds nothing on either layout — `Get-Content` is PowerShell, and
`user-data` is a workstation folder. An empty result there is not evidence that
the server refused nothing.

### Capturing a logcat that contains the failure

`adb logcat -c` clears the buffer and `adb logcat -d` dumps it and exits, so a
dump taken too early ends before the failure it was meant to show. Reproduce
the failure *first*, then dump:

```sh
adb logcat -c
# launch the app and reproduce the failure -- wait for the error on screen
adb logcat -d > NetworkError.txt
```

Check the end of the file before attaching it: the last timestamps should reach
the moment the error appeared, not the moment the app finished loading.
