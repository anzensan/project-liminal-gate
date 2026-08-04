# Installing the tools

**Most people should not read this page.** Run the doctor instead:

```sh
python3 -m liminal_gate.doctor --install-missing
```

It installs the JDK, the Android SDK packages, a pinned Android NDK
`llvm-objdump`, and Il2CppDumper, and records where they are so nothing below
about `PATH` or `JAVA_HOME` applies to you. Read on only if you want to install
a tool yourself, if the doctor could not cover your platform, or if you want to
know what it is doing on your behalf.

These are shell commands. Use **Terminal** on macOS, **PowerShell** on Windows,
or your usual shell on Linux — not the Python prompt, and not an Android Studio
code window.

## What the doctor does and does not do

| It installs | It does not install |
| --- | --- |
| A Temurin JDK 17, for `keytool` and for Gradle | **Android Studio**, which you still need for the emulator |
| Android SDK Platform-Tools, Build-Tools, and Platform 35, through Google's own `sdkmanager` | **An emulator system image or AVD** — create those in Android Studio |
| Android NDK r27d (`ndk;27.3.13750724`), solely for its AArch64-capable `llvm-objdump` | **A system-wide LLVM installation** — the NDK tool stays private under `user-data/` |
| Il2CppDumper v6.7.46, pinned | **A system-wide .NET runtime** — a private runtime is added only where the managed dumper needs one |
| A private .NET runtime, only where Il2CppDumper needs one | **Anything of Terra Battle's** — you still supply the APK and resources |

Directly downloaded archives are checked against their vendor-published
checksums before use; Google's `sdkmanager` verifies its SDK and NDK packages
from Google's repository metadata. Vendor tools and their records land under
`user-data/`, which Git ignores; required Python packages install into the
active Python environment. The doctor never edits a shell profile or registry.

Google's Android development tools do not support ARM-based Windows or Linux
hosts. The doctor refuses those SDK installs before downloading anything and
names the supported host choices; macOS supports both Intel and Apple silicon.

It will not accept the [Android SDK licences](https://developer.android.com/studio/terms)
for you. It prints them and asks; `--accept-android-sdk-licenses` answers in
advance if you have already read them.

### Where it put things

`user-data/toolchain.json` records the location of every tool the doctor found
or installed. Every setup command reads it at startup and puts those locations
into its own environment, which is why you do not need to export anything.

A variable you set yourself always wins. If you export `JAVA_HOME`, that is the
JDK setup uses, whatever the file says. To make the doctor's copy authoritative
again, unset yours. To start over, delete the file and run the doctor again.

## Installing the tools by hand

The rest of this page covers doing it yourself. Work through the section for
**your** operating system, then return to the
[README](../README.md#2-check-your-setup) and run the `--check` command. You do
not have to read the other two sections.

## What has to be installed

| Tool | Why it is needed |
| --- | --- |
| Python 3.11 or newer | Runs everything in this project. |
| Android Studio, with the Android Emulator and SDK tools | Optional: creates and manages an emulator. It is not needed when installing on a physical device and using the doctor's private SDK. |
| Android SDK Platform-Tools | Provides `adb`, which talks to the emulator or device. |
| Android SDK Build-Tools | Provide `zipalign` and `apksigner`, which sign the rebuilt APK. |
| A JDK | Provides `keytool`, which creates the local test signing key. Android Studio's bundled JDK is sufficient if its `bin` directory is on your `PATH`. |
| [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) | Recovers the master-data layout that an IL2CPP build strips. Without it a story clear cannot award a Companion. Setup runs it for you against your own APK. |
| An AArch64 disassembler | **LLVM** (`llvm-objdump`) on macOS and Windows, or `binutils-multiarch` on Linux. The Chapter 8–42 encounter map only exists as compiled code inside your APK, so reading it needs one. |
| Pinned Gradle 8.11.1 and Java 17–23 (on-device build only) | Builds the Android host. Setup verifies Gradle against its published SHA-256, caches it only below ignored `user-data/work/`, repairs its local launcher mode, and automatically uses a compatible Android Studio JDK when available. Do not commit a wrapper binary. |

You also need a local Terra Battle Android 5.5.7-170 APK and matching Android
resources. See [Files you supply](../README.md#files-you-supply).

## Install Android Studio's SDK components by hand

Skip this section when the doctor completed successfully. To manage the SDK or
an emulator through Android Studio instead, install it from the official Android
Developers site, then open
**Android Studio → Settings → Languages & Frameworks → Android SDK** (on some
versions: **More Actions → SDK Manager** on the welcome screen). In **SDK
Tools**, select **Android SDK Platform-Tools**, **Android Emulator**, and
**Android SDK Build-Tools**, then click **Apply**. The [Android SDK Manager
documentation](https://developer.android.com/tools/sdkmanager) explains the same
screen.

## macOS

If you are installing tools by hand instead of using the doctor's pinned NDK,
Homebrew provides the disassembler:

```sh
brew install llvm
```

Make the Android tools available in the current Terminal window:

```sh
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
```

To keep these for future Terminal windows, add the three `export` lines to
`~/.zshrc` and open a new Terminal window.

Confirm all four of these succeed before continuing:

```sh
ls "$ANDROID_HOME/platform-tools/adb"
adb version
java -version
keytool -help >/dev/null && echo "keytool is ready"
python3 --version
```

If `java` or `keytool` is missing, install a JDK and reopen Terminal. You can
also use Android Studio's bundled runtime by locating its `Contents/jbr/bin`
directory and adding that directory to `PATH`.

Then install Il2CppDumper — see [Il2CppDumper](#il2cppdumper) below.

## Windows

Open **PowerShell** and use the Android SDK location Android Studio normally
creates:

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:JAVA_HOME = "$env:LOCALAPPDATA\Programs\Android Studio\jbr"
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:ANDROID_HOME\cmdline-tools\latest\bin;$env:JAVA_HOME\bin;$env:Path"
Get-Command adb, java, keytool
py -3 --version
adb version
```

**The `JAVA_HOME` line matters and is easy to leave out.** `keytool` comes with a
**JDK**, not with the Android SDK, so none of the SDK directories contain it;
without that line `Get-Command keytool` fails even on a machine that has
everything installed. Android Studio ships its own runtime, and the path above is
where it normally lives. If Android Studio is installed for all users instead,
use `"$env:ProgramFiles\Android\Android Studio\jbr"`.

If `python3 --version` works on your Windows installation, you can use the
commands in this documentation exactly as written. Otherwise replace each
`python3 -m` with `py -3 -m`.

**Stop using `py -3` once a virtual environment is active.** Spelling out a
version makes the Windows launcher skip the active environment and run the
system Python instead, so `py -3 -m pip install` typed at a `(.venv)` prompt
installs somewhere the environment cannot see. Inside `(.venv)`, use plain
`python -m`, or name the interpreter directly as
`.\.venv\Scripts\python.exe -m`.

If `adb` or `keytool` is still not found after the lines above, install the
missing SDK/JDK component in Android Studio, reopen PowerShell, and repeat these
checks.

### If setup cannot find zipalign and apksigner

Guided setup automatically checks `ANDROID_SDK_ROOT`, `ANDROID_HOME`, and Android
Studio's usual Windows location, `%LOCALAPPDATA%\Android\Sdk`. If it still
reports those tools missing, first confirm the files exist (replace `36.0.0` with
the version installed on your PC):

```powershell
Get-ChildItem "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0\zipalign.exe", "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0\apksigner.bat"
```

Then either set the SDK root and rerun the normal command, or pass that exact
Build Tools version directory once:

```powershell
$env:ANDROID_SDK_ROOT = "$env:LOCALAPPDATA\Android\Sdk"
py -3 -m liminal_gate.tester_setup --build-tools "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.0.0" --port 8696 --device emulator-5570
```

Then install Il2CppDumper — see [Il2CppDumper](#il2cppdumper) below.

## Linux

If you are installing tools by hand instead of using the doctor's pinned NDK,
install the disassembler with your distribution's package manager:

```sh
sudo apt install binutils-multiarch    # Debian/Ubuntu
```

Use the equivalent SDK location and `PATH` entries as in the macOS section, with
the SDK path your distribution or Android Studio installed to. Confirm `adb`,
`java`, `keytool`, and `python3` all run before continuing.

Then install Il2CppDumper — see [Il2CppDumper](#il2cppdumper) below.

## Il2CppDumper

Il2CppDumper is a .NET program with no Homebrew formula. Download a release from
its own page, then either put the executable on your `PATH` or point
`LIMINAL_GATE_IL2CPPDUMPER` at it. That variable accepts the executable, the
directory you extracted the release to, or the `.dll` a cross-platform build
ships instead of an executable — which setup runs through `dotnet`.

On Windows the release is native, so there is an `Il2CppDumper.exe` to name. In
PowerShell:

```powershell
$env:LIMINAL_GATE_IL2CPPDUMPER = "C:\Tools\Il2CppDumper"
Test-Path $env:LIMINAL_GATE_IL2CPPDUMPER   # must print True
```

That variable lives only in the window you set it in, so run setup from that same
window. To keep it for future windows, set it once and open a new one:

```powershell
[Environment]::SetEnvironmentVariable("LIMINAL_GATE_IL2CPPDUMPER","C:\Tools\Il2CppDumper","User")
```

**Copying Il2CppDumper into this repository does not help**: it is looked for on
`PATH` and in that variable, never in the current directory.

## You do not need to copy tools into the project folder

You do not have to copy `adb.exe`, `keytool.exe`, or any other tool into the
project folder. Guided setup looks for both itself — `adb` in the SDK's
`platform-tools`, and `keytool` under `JAVA_HOME` and in Android Studio's bundled
runtime — and prints the path it settled on. If it reports one as unavailable,
that is worth an issue report rather than a copied executable.

## Optional: the Python image-extraction dependency

This derives the normal Pact banner images from your own resource bundles into
`user-data/`. It does not download or include game images. Pacts work without it.

```sh
python3 -m pip install ".[master-import]"
```

If that fails with **`error: externally-managed-environment`**, your Python does
not allow installing packages system-wide. This is normal for Homebrew Python on
macOS and for the system Python on many Linux distributions. Create a virtual
environment in the project folder instead:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install ".[master-import]"
```

Once activated, run the setup command from that same terminal, or it will not
find the newly installed package. Activate it again with
`source .venv/bin/activate` in any new terminal.

On Windows the activation command is `.venv\Scripts\activate` instead, and from
that `(.venv)` prompt install with plain `python -m pip install
".[master-import]"` — **not** `py -3`. The launcher skips the active environment
whenever a version is spelled out, so `py -3` installs into the system Python
while every later check reads `.venv`, which really is missing it. That reads as
a failed install even though the install succeeded; the giveaway is a check that
fails inside `(.venv)` and passes in a plain window.

If PowerShell refuses to activate with `running scripts is disabled on this
system`, skip activation rather than changing a policy: name the environment's
own interpreter, `.\.venv\Scripts\python.exe`, in place of `python3` for both
the install and every later command. See
[Windows and PowerShell](troubleshooting.md#windows-and-powershell).

If UnityPy or a required local Banner bundle is unavailable, setup reports the
exact reason and continues; normal Fellowship and Truth Pacts remain usable, but
their retired web-banner images will not be shown.

## Next

Return to the [README](../README.md#2-check-your-setup) and run:

```sh
python3 -m liminal_gate.tester_setup --check
```

## Optional: private on-device APK

Check the on-device route before it downloads/builds/installs anything:

```sh
python3 -m liminal_gate.on_device_setup --check
```

It requires the normal Android SDK/JDK tools, a complete `android-host/` source
tree, a reviewed local APK/resources, and (for installation) API 24+, at least
one supported Android ABI, and 4 GiB free in `/data`. Continue with
[Run the server inside the Android APK](on-device-setup.md); do not return to
the README's separate-server setup steps for this deployment mode.
