# Setup options and manual setup

Two things live here: the options the one-command guided setup accepts, and the
individual commands that guided setup runs for you. **You do not need the manual
steps for a normal install** — use them only to troubleshoot, or when you want to
see exactly what happens.

Run every `python3 -m liminal_gate...` command from the repository root. The
basic tester path needs no Python package installation or virtual environment.

## Guided setup options

The standard command is:

```sh
python3 -m liminal_gate.tester_setup --port 8696 --device emulator-5570
```

| Option | What it does |
| --- | --- |
| `--port` | The local TCP port. Four digits or fewer; see [Choose a port](device-setup.md#d-choose-a-port-with-at-most-four-digits). |
| `--device` | An emulator or physical device serial. `--emulator` is an older name for the same option. Omit it when only one target is connected; if several are ready, setup lists their serials and asks you to rerun with the intended one. |
| `--device-host` | This machine's LAN address, required when installing to a physical device. See [Install on a physical device](device-setup.md). |
| `--data-dir` | Where the save and generated files live. Use a separate one for a second player or a clean test. |
| `--prepare-only` | Build the APK without installing it or starting the server. |
| `--no-configure` | Non-interactive repeat of the standard setup. |
| `--replace-existing` | Uninstall a build made from a different checkout first. Clears that app's local data. |
| `--build-tools` | An explicit Android SDK Build Tools directory, for example `/path/to/sdk/build-tools/36.0.0`. Setup otherwise uses the newest usable installation, or `ANDROID_SDK_ROOT`. |
| `--prompt-key-password` | Choose the local signing key password yourself instead of having one generated. |
| `--check` | Report on every requirement and change nothing. |
| `--dummy-dll-dir`, `--dump-cs` | Reuse matching Il2CppDumper output you already have instead of the generated one. |
| `--event-catalog` | Replace the generated event rows with an independently prepared catalog; see below. |

Story chapters, Hunting zones, Daily Quests, Pacts, Companion draws and sales,
job unlocks, Rebirth, and status items are all enabled with no
feature-selection prompt. To
isolate one feature while troubleshooting, run `liminal_gate.bootstrap_server`
directly with only the flags you want; see
[advanced-configuration.md](advanced-configuration.md).

The command validates the inputs, creates the local manifests, creates a local
signing key on first use, patches and signs the APK, installs it on that one
device, then starts the local server in the foreground. Press Control-C when you
finish testing.

This starts a server for the one emulator or device you selected. Do not
port-forward it or use it as a hosted/public service.

### Overriding the generated event catalog

The curated 42-stage Archive, all 12 Tower solo-adapter stages, the 12
battle/banner-backed solo Eidolon stages, and the bundled Strikes Back families are enabled by standard
guided setup. Archive events, Tower, and solo Eidolon quests never interrupt
standard setup with a prompt — setup derives and validates them automatically.

If you have independently prepared a stricter reviewed catalog, add
`--event-catalog` to the normal setup command. Use `--dummy-dll-dir` only when you
want setup to reuse a matching local IL2CPP dump instead of its generated one.
Setup derives the matching character catalog and passes both runtime files to the
server. An override replaces the generated Special Quest, Tower, and Eidolon rows;
the bundled Strikes Back definitions remain authoritative. See [Advanced local
configuration](advanced-configuration.md#local-event-stages-and-character-grants).

You do not need to supply `DummyDll` yourself for normal guided setup: setup
generates and retains it automatically. See [What setup
generates](generated-files.md).

## Manual setup

Only if you need to troubleshoot.

### 1. Validate and map the local inputs

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
expected local layout. The second creates the local resource manifest used by the
server.

### 2. Create a local test signing key

You only need to do this once. **The password must be at least six characters** —
`keytool` rejects anything shorter, and it only says so after you have answered
the prompt. Run this from the repository root and choose a password when asked:

```sh
keytool -genkeypair -v \
  -keystore user-data/liminal-gate-test.keystore \
  -alias liminal-gate-test \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -dname "CN=Local Tester, OU=Testing, O=Project Liminal Gate, L=Local, ST=Local, C=US"
```

In PowerShell, use backticks for the line breaks, because the backslashes above
are a Unix shell convention that PowerShell does not accept:

```powershell
keytool -genkeypair -v `
  -keystore user-data/liminal-gate-test.keystore `
  -alias liminal-gate-test `
  -keyalg RSA `
  -keysize 2048 `
  -validity 10000 `
  -dname "CN=Local Tester, OU=Testing, O=Project Liminal Gate, L=Local, ST=Local, C=US"
```

The certificate identity is supplied automatically. It is local signing metadata
and stays on your machine. When `keytool` asks for the key password, press Return
to use the same password as the keystore.

Create the password file required by the signing command without placing the
password in shell history:

```sh
read -rs TEST_KEY_PASSWORD
printf '%s' "$TEST_KEY_PASSWORD" > user-data/keystore-password.txt
unset TEST_KEY_PASSWORD
chmod 600 user-data/keystore-password.txt
```

The PowerShell equivalent, which also writes the file without a trailing newline
and without leaving the password in your history:

```powershell
$TestKeyPassword = Read-Host -AsSecureString -Prompt "Local test-key password"
[System.IO.File]::WriteAllText(
  "$PWD\user-data\keystore-password.txt",
  [System.Net.NetworkCredential]::new("", $TestKeyPassword).Password
)
Remove-Variable TestKeyPassword
```

Enter the same password you chose for `keytool`. This guide uses this one file
for both keystore and key passwords.

### 3. Create and sign the redirected APK

For the standard Android emulator, the app reaches your host through `10.0.2.2`.
For a physical phone or tablet, substitute this machine's LAN address everywhere
`10.0.2.2` appears below, as described in [Install on a physical
device](device-setup.md).

Choose an unused local port now; the redirected APK and server must use the same
value. This guide uses `8002`, but any unused port with **four digits or fewer**
works — see [Choose a
port](device-setup.md#d-choose-a-port-with-at-most-four-digits) for why longer
ports are rejected:

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

For the exact final client, this plan also includes the Android 11+ ARM64
allocator compatibility edit. It is guarded by the selected Unity member's
SHA-256 and exact original bytes. Do not add `--drop-abi arm64-v8a` on a
64-bit-app-only device such as Pixel 7 or Pixel 7 Pro; that device cannot install
or run an armeabi-v7a-only package.

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
`--store-password-file` and `--key-password-file`; because this guide creates one
password, pass `user-data/keystore-password.txt` to both. There is no combined
`--keystore-password-file` option.

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

Success prints `wrote signed APK: user-data/liminal-gate-test.apk`. If you change
`LIMINAL_GATE_PORT` later, repeat this plan, patch, sign, and install sequence
before starting the server on the new port.

### 4. Start the server and install the APK

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

In another terminal, install to the emulator serial you identified earlier:

```sh
adb -s emulator-5556 install -r user-data/liminal-gate-test.apk
```

Replace `emulator-5556` with your intended emulator. If you exported
`ANDROID_SERIAL` in this terminal, omit `-s emulator-5556`:

```sh
adb install -r user-data/liminal-gate-test.apk
```
