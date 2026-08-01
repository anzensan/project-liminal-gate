# Installing the tools

Work through the section for **your** operating system, then return to the
[README](../README.md#2-check-your-setup) and run the `--check` command. You do
not have to read the other two sections.

These are shell commands. Use **Terminal** on macOS, **PowerShell** on Windows,
or your usual shell on Linux — not the Python prompt, and not an Android Studio
code window.

## What has to be installed

| Tool | Why it is needed |
| --- | --- |
| Python 3.11 or newer | Runs everything in this project. |
| Android Studio, with the Android Emulator and SDK tools | Creates the emulator and provides the SDK below. |
| Android SDK Platform-Tools | Provides `adb`, which talks to the emulator or device. |
| Android SDK Build-Tools | Provide `zipalign` and `apksigner`, which sign the rebuilt APK. |
| A JDK | Provides `keytool`, which creates the local test signing key. Android Studio's bundled JDK is sufficient if its `bin` directory is on your `PATH`. |
| [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) | Recovers the master-data layout that an IL2CPP build strips. Without it a story clear cannot award a Companion. Setup runs it for you against your own APK. |
| An AArch64 disassembler | **LLVM** (`llvm-objdump`) on macOS and Windows, or `binutils-multiarch` on Linux. The Chapter 8–42 encounter map only exists as compiled code inside your APK, so reading it needs one. |

You also need a local Terra Battle Android 5.5.7-170 APK and matching Android
resources. See [Files you supply](../README.md#files-you-supply).

## Install Android Studio's SDK components

Install Android Studio from the official Android Developers site, then open
**Android Studio → Settings → Languages & Frameworks → Android SDK** (on some
versions: **More Actions → SDK Manager** on the welcome screen). In **SDK
Tools**, select **Android SDK Platform-Tools**, **Android Emulator**, and
**Android SDK Build-Tools**, then click **Apply**. The [Android SDK Manager
documentation](https://developer.android.com/tools/sdkmanager) explains the same
screen.

## macOS

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

Install the disassembler with your distribution's package manager:

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
`source .venv/bin/activate` in any new terminal. On Windows the activation
command is `.venv\Scripts\activate` instead, and use
`py -3 -m pip install ".[master-import]"` when you use `py -3` for the other
commands.

If UnityPy or a required local Banner bundle is unavailable, setup reports the
exact reason and continues; normal Fellowship and Truth Pacts remain usable, but
their retired web-banner images will not be shown.

## Next

Return to the [README](../README.md#2-check-your-setup) and run:

```sh
python3 -m liminal_gate.tester_setup --check
```
