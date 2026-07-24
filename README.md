# Project Liminal Gate

☕ If you find this project helpful, consider [buying me a coffee!](https://buymeacoffee.com/ianderse).
Donations support all of my development projects, not only Project Liminal Gate.

> **Support policy:** contributions are voluntary and non-refundable. They do
> not purchase software, access, support, features, priority, or rights in
> Terra Battle or any original game material; this project remains source-only
> and separately licensed.

Project Liminal Gate is a local compatibility server for a playable
preservation path. The currently verified original-client path reaches and
clears Chapter 2-1. The guided setup also enables a bulk ordinary-story policy
for Chapter 2-2 through Chapter 42; it is not a claim that every later reward,
drop, or scripted scene has been historically reproduced.

## Current tester status

The guided setup now enables ordinary story progression beyond the tutorial,
through Chapter 42, and local ordinary Pacts:

- **Pact of Fellowship** uses Coins.
- **Pact of Truth** uses Energy; new local accounts receive 50 free Energy.

This remains a tester build. The original-client path is verified only through
Chapter 2-1, so later story stages may need individual compatibility fixes.
Fate, ticket, campaign, and event Pact variants are intentionally unsupported.
You can test on an Android emulator or on a physical phone or tablet; see
[Install on a physical phone or tablet](#install-on-a-physical-phone-or-tablet)
for the device path.

If you encounter a Network Error, please [open a GitHub issue](https://github.com/anzensan/project-liminal-gate/issues)
with the action you took, OS and emulator or device version, and the relevant
lines from `user-data/events.jsonl`.

## What you need

- Python 3.11 or newer, with `python3` available in a Terminal.
- Android Studio, including the Android Emulator and SDK tools.
- Android SDK Platform-Tools, which provides `adb`.
- Android SDK Build Tools, which provide `zipalign` and `apksigner`.
- A JDK, which provides Java's `keytool` command for creating a local test
  signing key. Android Studio's bundled JDK is sufficient if its `bin`
  directory is on your `PATH`.
- A local Terra Battle Android 5.5.7-170 APK and matching Android resources.

The APK and resources stay on your machine; this repository does not include
them. Keep all local inputs and generated files outside Git.

### Install and check the tools first

These are shell commands, so use **Terminal** on macOS (or a comparable shell
on Linux/Windows), not the Python prompt and not an Android Studio code
window. On macOS, install Android Studio from the official Android Developers
site, then open **Android Studio → Settings → Languages & Frameworks → Android
SDK** (on some versions: **More Actions → SDK Manager** on the welcome screen).
In **SDK Tools**, select **Android SDK Platform-Tools**, **Android Emulator**,
and **Android SDK Build-Tools**, then click **Apply**. The [Android SDK Manager
documentation](https://developer.android.com/tools/sdkmanager) explains the
same screen.

On macOS, make the tools available in the current Terminal window:

```sh
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
```

If `adb` still cannot be found, check that the SDK directory exists and that
Platform-Tools was installed:

```sh
ls "$ANDROID_HOME/platform-tools/adb"
adb version
java -version
keytool -help >/dev/null && echo "keytool is ready"
python3 --version
```

If `java` or `keytool` is missing, install a JDK and reopen Terminal. You can
also use Android Studio's bundled runtime by locating its `Contents/jbr/bin`
directory and adding that directory to `PATH`. Do not continue until all four
checks above succeed. To keep the Android paths for future Terminal windows,
add the three `export` lines to `~/.zshrc` and open a new Terminal window.

On Linux, use the equivalent SDK location and PATH entries. On Windows, open
**PowerShell** and use the Android SDK location normally created by Android
Studio:

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:ANDROID_HOME\cmdline-tools\latest\bin;$env:Path"
Get-Command adb, java, keytool
py -3 --version
adb version
```

If `python3 --version` works on your Windows installation, you can use the
commands below exactly as written. Otherwise replace each `python3 -m` with
`py -3 -m`. If `adb`, `java`, or `keytool` is not found, install the missing
SDK/JDK component in Android Studio, reopen PowerShell, and repeat these
checks.

The guided setup automatically checks `ANDROID_SDK_ROOT`, `ANDROID_HOME`, and
Android Studio's usual Windows location, `%LOCALAPPDATA%\\Android\\Sdk`. If it
still reports that `zipalign` and `apksigner` are missing, first confirm the
files exist (replace `36.0.0` with the version installed on your PC):

```powershell
Get-ChildItem "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0\zipalign.exe", "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0\apksigner.bat"
```

Then either set the SDK root and rerun the normal command, or pass that exact
Build Tools version directory once:

```powershell
$env:ANDROID_SDK_ROOT = "$env:LOCALAPPDATA\Android\Sdk"
py -3 -m liminal_gate.tester_setup --build-tools "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0" --port 8696 --device emulator-5570
```

## Quick start: emulator tester path

### 0. Open a Terminal in the project folder

Change into the folder you cloned or downloaded. The prompt should end in
`project-liminal-gate`; it must contain `README.md` and the `liminal_gate/`
directory:

```sh
cd /path/to/project-liminal-gate
ls README.md liminal_gate
```

Do not run the remaining commands from your home directory, from inside the
`liminal_gate/` subdirectory, or from another project. If the shell reports
`getcwd: cannot access parent directories`, first run `cd ~`, then `cd` back
to the real project directory.

### 1. Create and start an emulator

In Android Studio, open **Device Manager**. From the welcome screen, choose
**More Actions → Virtual Device Manager**. With a project open, choose
**View → Tool Windows → Device Manager**. These are the two official ways to
open it; see [Create and manage virtual devices](https://developer.android.com/studio/run/managing-avds).
Choose **Create device**, select a phone profile, choose a recent Android
system image, and start the new device. Use a fresh emulator profile for this
test build when possible.

The current known-good Windows report used a **Pixel 6 with Android 12** and
completed the verified path through Chapter 2-1. Some newer Android API levels
have caused the original APK to crash when opening game areas **on emulator
system images**. This has not been reproduced on physical hardware: a Samsung
tablet running a current Android release runs the same build correctly. Treat it
as an emulator image limitation rather than a general Android version limit, and
not as a local-server response. If you see an immediate crash on a newer image,
retry with a Pixel 6 Android 12 system image before investigating server logs.

Avoid Android 16 system images that use **16 KB page size**: the original APK
is not compatible with that emulator configuration. A standard, non-16-KB
Android 12 image is the recommended emulator baseline. The current setup already
recognizes Windows `zipalign.exe` and `apksigner.bat`; if it still reports those
tools missing, update to the latest project revision before editing any Python
files.

#### Start the emulator with `-gpu swangle`, especially on macOS

The emulator's default graphics backend can leave the app on a **permanently
black screen**. The app has not crashed and the server is not at fault: it
launches, talks to the server, and downloads resources normally, but the
emulator's OpenGL translator cannot complete the framebuffer Unity asks for, so
nothing is ever drawn. On macOS the default `-gpu auto` selects the Apple Metal
GLES translator, which fails this way.

Android Studio's Device Manager gives no way to pass this flag, so start the
emulator from a terminal instead:

```sh
"$HOME/Library/Android/sdk/emulator/emulator" -avd YOUR_AVD_NAME -gpu swangle
```

On Windows and Linux use the `emulator` binary in your own SDK directory. List
your AVD names with `emulator -list-avds`. `swangle` selects ANGLE with
SwiftShader, which renders correctly.

To confirm this is the problem rather than guess, count the framebuffer errors
while the black screen is showing:

```sh
adb logcat -d | grep -c 0x506
```

Thousands of `0x506` errors from `emuglGLESv2_enc` mean the graphics backend,
not the server. Zero means look elsewhere. This is worth checking early,
because the server log keeps showing successful `200` responses throughout, so
the failure looks like a server problem and is not one.

If you would rather test on a real phone or tablet, skip this step and see
[Install on a physical phone or tablet](#install-on-a-physical-phone-or-tablet).

Wait until the emulator has finished booting, then confirm that `adb` can see
it and print its serial number:

```sh
adb devices -l
```

The output should contain a line like `emulator-5570 device ...`. The first
column (`emulator-5570`) is the serial needed by the setup command. If it says
`offline` or `unauthorized`, wait for boot to finish and run the command again.
If you have other emulators or Android devices connected, use the intended
serial explicitly:

```sh
export ANDROID_SERIAL=emulator-5556
adb shell getprop ro.product.model
```

Replace `emulator-5556` with your serial. `ANDROID_SERIAL` applies only to the
current terminal, so it will not affect your other projects.

### 2. Arrange your local files

Create the local workspace first:

```sh
mkdir -p local-input/resources/data_u2017/android user-data
```

Then place your existing APK and resource categories in this layout. This
project does not provide download links or instructions for obtaining the APK
or resource pack. If you already have them, use Finder/Spotlight or a local
`find` search to locate them; the resource directory you need is the one whose
last two components are `data_u2017/android` and whose immediate children are
folders such as `BG`, `Scenario`, and `Pieces`:

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

The important resource folder is the final `android/` directory. It contains
the resource categories directly.

The setup command validates this before it modifies the APK. You may pass the
final `data_u2017/android` directory, or a parent directory that contains
`gdresources/data_u2017/android`; it detects the final Android folder and
prints the path it selected. Do not spell the folder `datau2017`—the underscore
in `data_u2017` is required.

For example, these searches only locate files already on your computer; they
do not download anything:

```sh
find "$HOME/Downloads" "$HOME/Desktop" -name 'terra-battle-5.5.7-170.apk' -print 2>/dev/null
find "$HOME/Downloads" "$HOME/Desktop" -type d -path '*/data_u2017/android' -print 2>/dev/null
```

The equivalent PowerShell searches are:

```powershell
Get-ChildItem "$HOME\Downloads", "$HOME\Desktop" -Recurse -File -Filter "terra-battle-5.5.7-170.apk" -ErrorAction SilentlyContinue
Get-ChildItem "$HOME\Downloads", "$HOME\Desktop" -Recurse -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like "*\data_u2017\android" }
```

### 3. One-command setup, install, and server start

After putting the APK and resources in the layout from step 2, run this one
command from the repository root:

Optional: install the local image-extraction dependency to derive the normal
Pact banner PNGs from your own resource bundles into `user-data/`. It does not
download or include game images in this repository:

```sh
python3 -m pip install ".[master-import]"
```

If that fails with **`error: externally-managed-environment`**, your Python
does not allow installing packages system-wide. This is normal for Homebrew
Python on macOS and for the system Python on many Linux distributions. Create a
virtual environment in the project folder instead:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install ".[master-import]"
```

Once activated, run the setup command from that same terminal, or it will not
find the newly installed package. Activate it again with
`source .venv/bin/activate` in any new terminal. On Windows the activation
command is `.venv\Scripts\activate` instead.

On Windows, use `py -3 -m pip install ".[master-import]"` when you use
`py -3` for the other commands. If UnityPy or a required local Banner bundle
is unavailable, setup reports the exact reason and continues; normal
Fellowship and Truth Pacts remain usable, but their retired web-banner images
will not be shown.

Choose a free local TCP port first. For example, this checks whether port 8696
is already in use on macOS:

```sh
lsof -nP -iTCP:8696 -sTCP:LISTEN
```

No output means the port is probably free. If a process is listed, choose a
different port and use that same number in both the setup command and any
manual server command.

In PowerShell, use this equivalent check:

```powershell
Get-NetTCPConnection -LocalPort 8696 -State Listen -ErrorAction SilentlyContinue
```

```sh
python3 -m liminal_gate.tester_setup --port 8696 --device emulator-5570
```

Replace the port and serial with yours. At the start, choose what you want to
test. The default is **Recommended — play the story and use normal Pacts**.
An advanced event question appears only for people who already have the
required local event catalog and DummyDll files. Press Enter to accept the
recommended choice. The command validates the inputs,
creates the local manifests, creates a local signing key on first use, patches
and signs the APK, installs it on that one device, then starts the local server
in the foreground. It asks for the signing-key password only on first setup and
saves it locally in `user-data/keystore-password.txt` with owner-only
permissions. Press Control-C when you finish testing.

`--device` takes an emulator serial or a physical phone or tablet serial;
`--emulator` still works as an older name for the same option. Installing on a
physical device additionally needs `--device-host`, because the default address
only works inside an emulator — see
[Install on a physical phone or tablet](#install-on-a-physical-phone-or-tablet).

The guided server includes the ordinary Chapter 2-42 progression policy. After
the verified Chapter 2-1 boundary, it accepts the normal client story flow,
unlocks stages in order, and handles chapter-map reveals without requiring a
separate server handler for each stage. It does **not** bundle an original
reward/drop table: ordinary clear results use the client-reported local result,
and unusual scripted stages may still stop with a Network Error until they are
given a specific compatibility rule.

It also enables local ordinary Pacts: **Pact of Fellowship** (`kind=0`) spends
3,000 Coins per pull, while **Pact of Truth** (`kind=1`) spends 5 Energy per
pull and accepts the normal 1, 5, or 10-pull form. New local accounts receive
50 free Energy so a tester can use Truth immediately. The included pools are
bounded local policy; selection is uniform and duplicate gains are local
defaults, not a claim about the retired service's per-character odds. Fate,
ticket, campaign, and event-specific Pact variants remain unsupported.

The 50-Energy starter grant applies when a local account is first created. To
test it after upgrading an existing setup, use a new local data directory and
clear only this test app's data before choosing **New Game** again:

```sh
python3 -m liminal_gate.tester_setup --data-dir user-data/pact-test --port 8696 --device emulator-5570
```

Then use the reset commands in [What to test](#5-what-to-test) with your own
serial and package name. This preserves your earlier `user-data/` test state.

If only one emulator or device is ready, omit `--device`. If several are ready,
the command lists their serials and asks you to rerun with the intended one. It
automatically uses the newest usable Android SDK Build Tools installation on
macOS. For another SDK location, set `ANDROID_SDK_ROOT` or pass, for example,
`--build-tools /path/to/sdk/build-tools/36.0.0`.

This starts a server for the one emulator or device you selected. Do not
port-forward it or use it as a hosted/public service.

To build the APK without installing or starting the server, add
`--prepare-only`.

For a non-interactive repeat of the standard setup, add `--no-configure`.

### Optional: enable a reviewed local event catalog

Events are not enabled by default. If you have independently prepared a
reviewed event catalog and the matching local `DummyDll` directory, add
`--dummy-dll-dir` and `--event-catalog` to the normal setup command. Setup
derives the required local character catalog and passes both local files to the
server. See [Advanced local configuration](docs/advanced-configuration.md#local-event-stages-and-character-grants).

### 4. Manual setup (only if you need to troubleshoot)

The basic tester path needs no Python package installation or virtual
environment. Run every `python3 -m liminal_gate...` command below from this
repository.

### 4a. Validate and map the local inputs

```sh
python3 -m liminal_gate.input_importer \
  --apk local-input/terra-battle-5.5.7-170.apk \
  --resource-root local-input/resources/data_u2017/android \
  --output-dir user-data/input-manifest \
  --reviewed-android-5-5-7

python3 -m liminal_gate.resource_catalog_builder \
  --resource-root local-input/resources/data_u2017/android \
  --output-manifest user-data/resources.json
```

These commands do not start a server or alter the APK. The first validates the
expected local layout. The second creates the local resource manifest used by
the server.

### 4b. Create a local test signing key

You only need to do this once. Run this from the repository root and choose a
password when prompted:

```sh
keytool -genkeypair -v \
  -keystore user-data/liminal-gate-test.keystore \
  -alias liminal-gate-test \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -dname "CN=Local Tester, OU=Testing, O=Project Liminal Gate, L=Local, ST=Local, C=US"
```

The certificate identity is supplied automatically. It is local signing
metadata and stays on your machine. When `keytool` asks for the key password,
press Return to use the same password as the keystore.

Create the password file required by the signing command without placing the
password in shell history:

```sh
read -rs TEST_KEY_PASSWORD
printf '%s' "$TEST_KEY_PASSWORD" > user-data/keystore-password.txt
unset TEST_KEY_PASSWORD
chmod 600 user-data/keystore-password.txt
```

Enter the same password you chose for `keytool`. The README uses this one file
for both keystore and key passwords.

### 4c. Create and sign the redirected APK

For the standard Android emulator, the app reaches your host through
`10.0.2.2`. For a physical phone or tablet, substitute this machine's LAN
address everywhere `10.0.2.2` appears below, as described in
[Install on a physical phone or tablet](#install-on-a-physical-phone-or-tablet).

Choose an unused local port now; the redirected APK and server must use the
same value. This guide uses `8002`, but any unused port with **four digits or
fewer** works — see [Choose a port](#d-choose-a-port-with-at-most-four-digits)
for why longer ports are rejected:

```sh
export LIMINAL_GATE_PORT=8002
```

Create the local redirect plan and apply it:

```sh
python3 -m liminal_gate.legacy_client_apk_plan \
  --source-apk local-input/terra-battle-5.5.7-170.apk \
  --server-origin "http://10.0.2.2:${LIMINAL_GATE_PORT}" \
  --output-plan user-data/local-server-plan.json

python3 -m liminal_gate.apk_patcher \
  --source-apk local-input/terra-battle-5.5.7-170.apk \
  --patch-plan user-data/local-server-plan.json \
  --output-apk user-data/liminal-gate-unsigned.apk
```

Then find the Android SDK Build Tools directory. On macOS, Android Studio uses
this location by default:

```sh
SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}"
ls "$SDK_ROOT/build-tools"
```

Choose one version printed by that command and set the directory once. For
example, if it printed `36.0.0`:

```sh
BUILD_TOOLS="$SDK_ROOT/build-tools/36.0.0"
```

Then sign with your own Android tools and key. The signer requires both
`--store-password-file` and `--key-password-file`; because this guide creates
one password, pass `user-data/keystore-password.txt` to both. There is no
combined `--keystore-password-file` option.

```sh
python3 -m liminal_gate.apk_signer \
  --unsigned-apk user-data/liminal-gate-unsigned.apk \
  --output-apk user-data/liminal-gate-test.apk \
  --zipalign "$BUILD_TOOLS/zipalign" \
  --apksigner "$BUILD_TOOLS/apksigner" \
  --keystore user-data/liminal-gate-test.keystore \
  --key-alias liminal-gate-test \
  --store-password-file user-data/keystore-password.txt \
  --key-password-file user-data/keystore-password.txt
```

Success prints `wrote signed APK: user-data/liminal-gate-test.apk`. If you
change `LIMINAL_GATE_PORT` later, repeat this plan, patch, sign, and install
sequence before starting the server on the new port.

### 4d. Start the server and install the APK

In the terminal that will run the server, set the same port again (environment
variables do not carry into another terminal). Keep it running while you test:

```sh
export LIMINAL_GATE_PORT=8002

python3 -m liminal_gate.bootstrap_server \
  --profile profiles/legacy-client-bootstrap.json \
  --state-file user-data/bootstrap-state.json \
  --host 0.0.0.0 \
  --port "$LIMINAL_GATE_PORT" \
  --event-log user-data/events.jsonl \
  --resource-root local-input/resources/data_u2017/android \
  --resource-manifest user-data/resources.json
```

In another terminal, install to the emulator serial you identified in step 1:

```sh
adb -s emulator-5556 install -r user-data/liminal-gate-test.apk
```

Replace `emulator-5556` with your intended emulator. If you exported
`ANDROID_SERIAL` in this terminal, omit `-s emulator-5556`:

```sh
adb install -r user-data/liminal-gate-test.apk
```

### 5. What to test

Use a fresh state file, then complete the normal client flow:

1. Title screen → New Game → tutorial summons and party steps.
2. Complete Borderlands 1-1 through 1-5.
3. On World Map, select `Ch 2: To the Capital` and complete section 1.
4. Confirm section 2 is marked **New** and World Map shows **210 Coins**.
5. Stop and relaunch the app with the same server state. Progress and the
   210-Coin display should resume.

Chapter 2-2 is the current expected stopping point. The app data on the
emulator or device and the server state file are a matched pair. To begin
another clean test without overwriting an earlier run, use another state-file
name, such as `--state-file user-data/tester-2.json`, and clear data for this
test app on the selected emulator or device before choosing **New Game** again:

```sh
adb -s emulator-5556 shell pm list packages | grep -Ei 'terra|mist'
adb -s emulator-5556 shell pm clear YOUR_TERRA_BATTLE_PACKAGE
```

Replace `emulator-5556` with your own serial — a physical device serial works
the same way — and `YOUR_TERRA_BATTLE_PACKAGE` with the value shown by the
first command. This clears only that app's local data on that one target; it
does not remove the APK or affect anything else.

## Install on a physical phone or tablet

The emulator path above reaches the server through `10.0.2.2`, an alias that
only exists inside an Android emulator. A real device has to be told this
machine's own address on your network instead. Everything else — the file
layout in step 2, the signing key, the server itself — is unchanged.

This is still a private, local-network setup. Do not port-forward the server,
expose it to the internet, or use it as a hosted service.

### A. Prepare the device

Enable **Developer options** (Settings → About → tap **Build number** seven
times), then turn on **USB debugging** inside Developer options. Connect the
device by USB, and accept the **Allow USB debugging** prompt that appears on
the device screen. Then confirm your computer can see it:

```sh
adb devices -l
```

A physical device shows a hardware serial rather than an `emulator-NNNN` name,
for example `R52T80ABCDE   device  ...`. If it says `unauthorized`, the
on-device prompt has not been accepted yet. If nothing is listed, try a
different cable — charge-only USB cables are a common cause.

### B. Find this machine's network address

```sh
ipconfig getifaddr en0        # macOS, Wi-Fi
hostname -I | awk '{print $1}'  # Linux
```

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -ne 'WellKnown' }
```

You want a private LAN address, normally starting `192.168.`, `10.`, or
`172.16.`–`172.31.`. The phone or tablet must be on **the same network**: the
same router, and not on a guest or client-isolated Wi-Fi network, which blocks
devices from reaching each other.

### C. Keep that address from changing

The server address is compiled into the APK when it is patched. This is the
single most important thing to understand about the device path:

> **If this machine's address changes, the installed app stops working.** It
> will not find the new address by itself. You have to rerun setup and
> reinstall the APK.

Most home routers hand out addresses by DHCP and can change them after a reboot
or a lease expiry. Pick one of these, best first:

1. **Reserve the address on your router (recommended).** In the router's admin
   page, find DHCP reservations (sometimes "static lease" or "bind IP to MAC")
   and reserve the current address for this machine's MAC address. The machine
   keeps using DHCP, so nothing changes locally, but the address stops moving.
2. **Configure a static address on this machine.** Set it manually in your OS
   network settings, choosing an address **outside** the router's DHCP range so
   nothing else is handed the same one.
3. **Do nothing and accept the breakage.** Fine for a single afternoon of
   testing. When the address changes, rerun the setup command with the new one;
   your saved game data in `user-data/` is not affected.

### D. Choose a port with at most four digits

The redirect works by overwriting text already inside the APK, and the
replacement can never be longer than what it replaces. That leaves room for
**27 characters total**, counting `http://`, the address, the colon, and the
port.

The longest possible IPv4 address is 15 characters, so:

```text
http://192.168.100.100:8696     27 characters  works
http://192.168.100.100:18696    28 characters  rejected
```

Any address on your network fits **as long as the port has four digits or
fewer**. Setup checks this before it touches the APK and tells you the measured
length if it does not fit. Host *names* are usually too long and are not
recommended in any case, because Android does not reliably resolve local
`.local` names.

### E. Run setup against the device

Use the address from step B and the serial from step A:

```sh
python3 -m liminal_gate.tester_setup \
  --device-host 192.168.1.10 \
  --device R52T80ABCDE \
  --port 8696
```

Setup prints the address it baked in, so you can confirm it:

```text
This build reaches the server at http://192.168.1.10:8696 and only that address.
```

`--device` may be omitted when only one device is connected. It accepts an
emulator serial equally well, so `--emulator` still works as an older name for
the same option. To build the APK without installing, add `--prepare-only`.

Setup checks the target before it builds anything. If the selected serial does
not look like an emulator and `--device-host` was left at its emulator-only
default, it stops and says so, rather than producing an APK that cannot reach
the server. An emulator attached over TCP has an address-style serial and can
trip this too; pass `--device-host 10.0.2.2` explicitly in that case.

Addresses meaning "this same device" are also rejected: `localhost`,
`127.0.0.1`, and `0.0.0.0` name the phone or tablet itself from the client's
point of view, never the machine running the server. Pass only the address in
`--device-host`, and set the port with `--port`.

If a build from a different checkout is already installed, Android refuses to
replace it, because each checkout creates its own local test signing key. Add
`--replace-existing` to uninstall it first. That clears the app's local data on
the device, so it downloads resources again and starts a new local account;
setup never does it without being asked.

### F. First run over Wi-Fi

The first launch downloads the whole local resource set — roughly 11,800 files.
Over Wi-Fi this takes noticeably longer than the emulator path, which reads
from this machine's own loopback. Keep the device awake and plugged in, prefer
a 5 GHz network, and let the first run finish before judging performance.

If the app shows Network Error immediately at launch, check in this order:
the two devices are on the same network; the server is running and was started
with `--host 0.0.0.0`; the address printed by setup still matches the output of
step B; and any firewall on this machine allows inbound connections on your
chosen port.

## Troubleshooting

| What you see | What to do |
| --- | --- |
| `No module named liminal_gate` | Run the command from the repository root: the folder containing `README.md` and `liminal_gate/`. |
| Black screen after launching the app, no crash, server log shows `200` responses | The emulator's graphics backend cannot complete Unity's framebuffer. Restart the emulator from a terminal with `-gpu swangle`. Confirm with `adb logcat -d \| grep -c 0x506`: thousands of those errors mean graphics, not the server. See [Start the emulator with `-gpu swangle`](#start-the-emulator-with--gpu-swangle-especially-on-macos). |
| `error: externally-managed-environment` from `pip install` | Your Python does not allow system-wide installs, which is normal for Homebrew Python. Use a virtual environment, then run setup from that same activated terminal. See [step 3](#3-one-command-setup-install-and-server-start). |
| `Pact banner preparation skipped: ... requires UnityPy` | Only the retired Pact banner images are missing; Pacts themselves work. Install the optional dependency as above if you want the images. |
| `/gd/login` returns 401 or the title screen immediately shows Network Error after a server-state change | The emulator's saved account does not exist in the chosen server state file. Start with a new state-file name and clear the selected emulator app's data using the reset commands above. |
| The signing command exits without output | Update an older checkout with `git pull --ff-only`, then rerun the command. A successful current version prints the signed APK path. |
| `APK signing failed: zipalign/apksigner is unavailable` | Set `BUILD_TOOLS` to one of the directories printed by `ls "$SDK_ROOT/build-tools"`; do not use the literal placeholder path from an older guide. |
| `adb devices` shows no emulator | Start an emulator from Android Studio Device Manager, then run `adb devices` again. |
| `adb devices` does not list a connected phone or tablet | Enable USB debugging and accept the on-device authorization prompt; if still absent, try another USB cable, since charge-only cables carry no data. |
| `server origin ... allow at most 27` | The address and port do not fit in the space available inside the APK. Use a port with four digits or fewer, and an IP address rather than a host name. See [Choose a port](#d-choose-a-port-with-at-most-four-digits). |
| `does not look like an emulator, and --device-host is still ...` | You are installing to a physical device but did not pass `--device-host`. Pass this machine's LAN address. If the target really is an emulator attached over TCP, pass `--device-host 10.0.2.2` explicitly. |
| `--device-host ... refers to the client's own device` | `localhost`, `127.0.0.1`, and `0.0.0.0` mean the phone or tablet itself. Use `10.0.2.2` for an emulator or this machine's LAN address for a device. |
| `--device-host must not contain a port` | Pass only the address in `--device-host` and set the port separately with `--port`. |
| A device that worked yesterday now shows Network Error | This machine's network address probably changed. Recheck it, then rerun setup and reinstall. See [Keep that address from changing](#c-keep-that-address-from-changing). |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` / `signatures do not match` | A build made from a different checkout, with a different local test key, is already installed. Rerun with `--replace-existing`, or uninstall it yourself with `adb -s YOUR_SERIAL uninstall com.mistwalkercorp.guardians`. Either way that app's local data is cleared, so it downloads resources again and starts a new local account. |
| `keytool: command not found` | Install a JDK, then reopen the terminal and rerun the signing-key step. |
| Input validation rejects the resource root | Use `local-input/resources/data_u2017/android`, not `local-input/resources`. |
| Network Error before the title flow | Confirm the server uses `--host 0.0.0.0` and the same port embedded in the APK. If you change the port, rerun the plan, patch, sign, and install steps; then inspect `tail -n 20 user-data/events.jsonl`. |
| Android refuses to install the APK | Use a clean emulator profile or remove the differently signed prior test build. |
| Resource-manifest error on server start | Confirm the resource root, then rerun `python3 -m liminal_gate.resource_catalog_builder`. |
| Sound is distorted, cuts out, or does not return | Check `user-data/events.jsonl` for `404` requests beneath `/resources/SE/`. A missing sound bundle in the local resource set can cause this; include those paths in the issue report. |
| A request fails after Chapter 2-1 | Ordinary core-story progression is enabled, but a scripted reward/drop exception may still be unsupported. Record the route, chapter/section, steps, and sanitized event log. |

For a local client-to-server failure, open the GitHub **Network error** issue
form with the setup commands, client actions, last screen reached, expected
result, actual result, and a sanitized `user-data/events.jsonl` excerpt. Do
not attach APKs, resources, captures, account saves, tokens, digests, or keys.

## More documentation

- [Advanced local configuration](docs/advanced-configuration.md) — optional
  progression, outcome, inventory, Pact, Companion, and other local catalogs.
- [Developer reference](docs/developer-reference.md) — server modes, custom
  profiles, resource serving, APK tools, and release checks.
- [Compatibility scope](COMPATIBILITY_SCOPE.md) — supported operations and
  confidence labels.
- [Parity roadmap](PARITY_ROADMAP.md) — known gaps and future work.
- [Contributing](CONTRIBUTING.md) — issue-reporting expectations.

Project Liminal Gate is source-available under the
[PolyForm Noncommercial 1.0.0](LICENSE) license.
