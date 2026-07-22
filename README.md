# Project Liminal Gate

☕ If you find this project helpful, consider [buying me a coffee!](https://buymeacoffee.com/ianderse).
Donations support all of my development projects, not only Project Liminal Gate.

> **Support policy:** contributions are voluntary and non-refundable. They do
> not purchase software, access, support, features, priority, or rights in
> Terra Battle or any original game material; this project remains source-only
> and separately licensed.

Project Liminal Gate is a local compatibility server for a narrow, playable
preservation test path. The currently verified path reaches and clears Chapter
2-1. It is not a complete replacement for the original online service.

## What you need

- Python 3.11 or newer.
- An Android emulator with `adb` available.
- Android SDK Build Tools: `zipalign` and `apksigner`.
- Java's `keytool` command for creating a local test signing key.
- A local Terra Battle Android 5.5.7-170 APK and matching Android resources.

The APK and resources stay on your machine; this repository does not include
them. Keep all local inputs and generated files outside Git.

## Quick start: emulator tester path

### 0. Open a terminal in the project folder

Change into the folder you cloned or downloaded. It must contain `README.md`
and the `liminal_gate/` directory:

```sh
cd /path/to/project-liminal-gate
ls README.md liminal_gate
```

Do not run the remaining commands from your home directory or another project.

### 1. Create and start an emulator

In Android Studio, open **Device Manager**, choose **Create device**, select a
phone profile, choose a recent Android system image, and start the new device.
Use a fresh emulator profile for this test build when possible.

Confirm that `adb` can see it, including its serial number:

```sh
adb devices -l
```

Find the intended emulator's serial (for example, `emulator-5556`). If you have
other emulators or Android devices connected, use that serial explicitly in the
install command below. You can also pin this terminal to it:

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

Then place your existing APK and resource categories in this layout:

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

### 3. One-command setup, install, and server start

After putting the APK and resources in the layout from step 2, run this one
command from the repository root:

```sh
python3 -m liminal_gate.tester_setup --port 8696 --emulator emulator-5570
```

Replace the port and emulator serial with yours. The command validates the
inputs, creates the local manifests, creates a local signing key on first use,
patches and signs the APK, installs it on that one emulator, then starts the
local server in the foreground. It asks for the signing-key password only on
first setup and saves it locally in `user-data/keystore-password.txt` with
owner-only permissions. Press Control-C when you finish testing.

If only one emulator is ready, omit `--emulator`. If several are ready, the
command lists their serials and asks you to rerun with the intended one. It
automatically uses the newest usable Android SDK Build Tools installation on
macOS. For another SDK location, set `ANDROID_SDK_ROOT` or pass, for example,
`--build-tools /path/to/sdk/build-tools/36.0.0`.

This starts a server for your selected local emulator only. Do not port-forward
it or use it as a hosted/public service.

To build the APK without installing or starting the server, add
`--prepare-only`.

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
`10.0.2.2`. Choose an unused local port now; the redirected APK and server
must use the same value. This guide uses `8002`, but any unused port works:

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

Chapter 2-2 is the current expected stopping point. The emulator's app data
and the server state file are a matched pair. To begin another clean test
without overwriting an earlier run, use another state-file name, such as
`--state-file user-data/tester-2.json`, and clear data for this test app on
the selected emulator before choosing **New Game** again:

```sh
adb -s emulator-5556 shell pm list packages | grep -Ei 'terra|mist'
adb -s emulator-5556 shell pm clear YOUR_TERRA_BATTLE_PACKAGE
```

Replace `emulator-5556` and `YOUR_TERRA_BATTLE_PACKAGE` with the values shown
by the first command. This clears only that app's local data on that emulator;
it does not remove the APK or alter another emulator.

## Troubleshooting

| What you see | What to do |
| --- | --- |
| `No module named liminal_gate` | Run the command from the repository root: the folder containing `README.md` and `liminal_gate/`. |
| `/gd/login` returns 401 or the title screen immediately shows Network Error after a server-state change | The emulator's saved account does not exist in the chosen server state file. Start with a new state-file name and clear the selected emulator app's data using the reset commands above. |
| The signing command exits without output | Update an older checkout with `git pull --ff-only`, then rerun the command. A successful current version prints the signed APK path. |
| `APK signing failed: zipalign/apksigner is unavailable` | Set `BUILD_TOOLS` to one of the directories printed by `ls "$SDK_ROOT/build-tools"`; do not use the literal placeholder path from an older guide. |
| `adb devices` shows no emulator | Start an emulator from Android Studio Device Manager, then run `adb devices` again. |
| `keytool: command not found` | Install a JDK, then reopen the terminal and rerun the signing-key step. |
| Input validation rejects the resource root | Use `local-input/resources/data_u2017/android`, not `local-input/resources`. |
| Network Error before the title flow | Confirm the server uses `--host 0.0.0.0` and the same port embedded in the APK. If you change the port, rerun the plan, patch, sign, and install steps; then inspect `tail -n 20 user-data/events.jsonl`. |
| Android refuses to install the APK | Use a clean emulator profile or remove the differently signed prior test build. |
| Resource-manifest error on server start | Confirm the resource root, then rerun `python3 -m liminal_gate.resource_catalog_builder`. |
| A request fails after Chapter 2-1 | That is outside the current basic tester path. Record the route and steps if it happens before the stated boundary. |

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
